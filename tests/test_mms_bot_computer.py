import json
import re
import subprocess
from pathlib import Path

import pytest

from mms_web.bot_computer import EgoComputer
from mms_web.errors import WebError


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (2).to_bytes(4, "big") + (3).to_bytes(4, "big")


def _input(script: str) -> dict:
    match = re.search(r"const input = (.*);", script)
    assert match
    return json.loads(match.group(1))


def test_capture_uses_one_persistent_space_and_validates_png(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, *, input, text, capture_output, timeout, check):
        assert command == ["fake-ego", "nodejs"]
        assert text and capture_output and timeout > 0 and check is False
        payload = _input(input)
        calls.append(payload)
        if payload["operation"] == "create":
            return subprocess.CompletedProcess(command, 0, '{"spaceId":7,"page":"p1"}\n', "")
        output = Path(payload["outputPath"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(PNG)
        return subprocess.CompletedProcess(command, 0, json.dumps({"spaceId": 7, "page": "p1", "path": str(output)}) + "\n", "")

    monkeypatch.setattr("mms_web.bot_computer.subprocess.run", fake_run)
    computer = EgoComputer(tmp_path / "state", executable="fake-ego")
    first = computer.capture("task_1", "https://example.com/path")
    second = computer.capture("task_1")

    assert first["kind"] == "screenshot"
    assert first["width"] == 2 and first["height"] == 3
    assert first["sha256"]
    assert first["spaceId"] == 7 and second["spaceId"] == 7
    assert Path(first["path"]).is_relative_to(tmp_path / "state" / "bots" / "screenshots" / "task_1")
    assert [entry["operation"] for entry in calls] == ["create", "capture", "capture"]
    assert calls[1]["url"] == "https://example.com/path"
    assert (tmp_path / "state" / "bots" / "ego-spaces.json").is_file()


def test_missing_cli_is_explicit_and_does_not_write_state(tmp_path):
    with pytest.raises(WebError) as failure:
        EgoComputer(tmp_path / "state", executable="").capture("task_1")
    assert failure.value.code == "EGO_UNAVAILABLE"
    assert not (tmp_path / "state" / "bots").exists()


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///tmp/a.png", "ftp://example.com", "//example.com"])
def test_capture_rejects_unsafe_url_before_creating_space(tmp_path, monkeypatch, url):
    monkeypatch.setattr("mms_web.bot_computer.subprocess.run", lambda *args, **kwargs: pytest.fail("Ego must not run"))
    with pytest.raises(WebError) as failure:
        EgoComputer(tmp_path / "state", executable="fake-ego").capture("task_1", url)
    assert failure.value.code == "INVALID_URL"
    assert not (tmp_path / "state" / "bots").exists()


def test_capture_refuses_browser_reported_path_outside_task_directory(tmp_path, monkeypatch):
    def fake_run(command, *, input, **kwargs):
        payload = _input(input)
        if payload["operation"] == "create":
            return subprocess.CompletedProcess(command, 0, '{"spaceId":8}\n', "")
        expected = Path(payload["outputPath"])
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_bytes(PNG)
        return subprocess.CompletedProcess(command, 0, '{"spaceId":8,"path":"/tmp/outside.png"}\n', "")

    monkeypatch.setattr("mms_web.bot_computer.subprocess.run", fake_run)
    with pytest.raises(WebError) as failure:
        EgoComputer(tmp_path / "state", executable="fake-ego").capture("task_1")
    assert failure.value.code == "EGO_INVALID_OUTPUT"



def test_ego_stderr_console_receipt_is_supported():
    result = subprocess.CompletedProcess(['ego-browser', 'nodejs'], 0, '', '{"spaceId":12,"page":"p1"}\n\n')
    assert EgoComputer._receipt(result) == {'spaceId': 12, 'page': 'p1'}


def test_action_script_uses_persistent_page_api():
    script = EgoComputer._action_script(12, "fill", "loc=css:#name", "Xin")
    assert "taskSpace(input.spaceId)" in script
    assert "page.fill(input.target, input.value)" in script
    assert "page('p1')" in script
