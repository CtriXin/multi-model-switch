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
    fixed, gone = gate.classify_repairs(
        base_failures={"tests/a.py::red_then_fixed", "tests/a.py::red_then_deleted"},
        head_failures=set(),
        head_present={"tests/a.py::red_then_fixed", "tests/a.py::always_green"},
    )
    assert fixed == ["tests/a.py::red_then_fixed"]
    assert gone == ["tests/a.py::red_then_deleted"]


def test_a_test_still_failing_is_neither_repaired_nor_gone():
    gate = _gate()
    fixed, gone = gate.classify_repairs(
        base_failures={"tests/a.py::still_red"},
        head_failures={"tests/a.py::still_red"},
        head_present={"tests/a.py::still_red"},
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
    failures, collected, present = gate.parse_report(report, tmp_path)
    assert failures == {"tests/test_x.py::fails"}
    assert collected == 3
    # A skipped test still exists; only a test that stopped existing is absent.
    assert present == {
        "tests/test_x.py::passes", "tests/test_x.py::fails", "tests/test_x.py::skipped"}
