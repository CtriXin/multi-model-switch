"""The regression gate must not let a deleted red test read as a repair."""
from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _gate():
    spec = importlib.util.spec_from_file_location(
        "ci_pytest_regression", ROOT / "scripts" / "ci_pytest_regression.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_deleted_red_test_is_not_counted_as_repaired():
    gate = _gate()
    fixed, gone, unverified = gate.classify_repairs(
        base_failures={"tests/a.py::red_then_fixed", "tests/a.py::red_then_deleted"},
        head_failures=set(),
        head_present={"tests/a.py::red_then_fixed", "tests/a.py::always_green"},
        head_passed={"tests/a.py::red_then_fixed", "tests/a.py::always_green"},
    )
    assert fixed == ["tests/a.py::red_then_fixed"]
    assert gone == ["tests/a.py::red_then_deleted"]


def test_a_test_still_failing_is_neither_repaired_nor_gone():
    gate = _gate()
    fixed, gone, unverified = gate.classify_repairs(
        base_failures={"tests/a.py::still_red"},
        head_failures={"tests/a.py::still_red"},
        head_present={"tests/a.py::still_red"},
        head_passed=set(),
    )
    assert fixed == [] and gone == []


def test_parse_report_reports_which_tests_ran_not_only_which_failed(tmp_path):
    gate = _gate()
    # _node_id rebuilds "tests.test_x" into a path by asking the checkout which
    # prefix is a real file, so the checkout has to contain it.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("", encoding="utf-8")
    report = tmp_path / "report.xml"
    report.write_text(textwrap.dedent("""\
        <?xml version="1.0" encoding="utf-8"?>
        <testsuites><testsuite name="pytest">
          <testcase classname="tests.test_x" name="passes"/>
          <testcase classname="tests.test_x" name="fails"><failure>boom</failure></testcase>
          <testcase classname="tests.test_x" name="skipped"><skipped/></testcase>
        </testsuite></testsuites>
        """), encoding="utf-8")
    failures, collected, present, details, passed = gate.parse_report(report, tmp_path)
    assert failures == {"tests/test_x.py::fails"}
    assert collected == 3
    assert passed == {"tests/test_x.py::passes"}
    assert details == {"tests/test_x.py::fails": "boom"}
    # A skipped test still exists; only a test that stopped existing is absent.
    assert present == {
        "tests/test_x.py::passes", "tests/test_x.py::fails", "tests/test_x.py::skipped"}



def _run_synthetic_gate(tmp_path, monkeypatch, capsys, base_source, head_source):
    """Exercise main -> run_suite -> real pytest -> JUnit, with disposable checkouts."""
    gate = _gate()
    base, head = tmp_path / "base", tmp_path / "head"
    for checkout, source in [(base, base_source), (head, head_source)]:
        (checkout / "tests").mkdir(parents=True)
        (checkout / "tests/test_sample.py").write_text(source, encoding="utf-8")
    monkeypatch.setattr(gate, "REPO_ROOT", head)
    monkeypatch.setattr(gate, "base_worktree", lambda ref: base)
    # Checkout lifecycle is the only fake boundary; run_suite is unmodified.
    monkeypatch.setattr(gate, "_run", lambda *args, **kwargs: None)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(sys, "argv", ["gate", "--base", "fixture", "--report-dir", str(tmp_path / "reports")])
    result = gate.main()
    return result, capsys.readouterr().out


def test_main_only_calls_an_executed_pass_repaired(tmp_path, monkeypatch, capsys):
    names = ["fixed", "skipped", "xfail", "gone"]
    base = "\n".join(f"def test_{name}(): assert False" for name in names)
    head = "import pytest\ndef test_fixed(): pass\ndef test_skipped(): pytest.skip('fixture')\ndef test_xfail(): pytest.xfail('fixture')\n"
    result, output = _run_synthetic_gate(tmp_path, monkeypatch, capsys, base, head)
    assert result == 0
    assert "Repaired by this PR (1)" in output
    assert "  + tests/test_sample.py::test_fixed" in output
    assert "  ~ tests/test_sample.py::test_gone" in output
    for name in ["skipped", "xfail"]:
        assert f"  ? tests/test_sample.py::test_{name}" in output
        assert f"  + tests/test_sample.py::test_{name}" not in output
    assert "::warning title=Red tests disappeared" in output
    assert "::warning title=Red tests skipped" in output


@pytest.mark.parametrize("outcome", ["skip", "xfail"])
def test_main_does_not_clear_a_regression_when_its_rerun_skips(tmp_path, monkeypatch, capsys, outcome):
    base = "def test_changed(): pass\n"
    head = ("import pytest\nfrom pathlib import Path\ndef test_changed():\n"
            "    flag = Path(__file__).with_suffix('.ran')\n"
            f"    if flag.exists(): pytest.{outcome}('fixture')\n"
            "    flag.write_text('ran')\n    assert False, 'real regression'\n")
    result, output = _run_synthetic_gate(tmp_path, monkeypatch, capsys, base, head)
    assert result == 1
    assert "Broken by this PR (1)" in output
    assert "  - tests/test_sample.py::test_changed" in output
    assert "No test that passes on the base commit fails here" not in output
