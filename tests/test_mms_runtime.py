import sys


def test_runtime_accepts_current_supported_python():
    import mms_runtime

    assert sys.version_info >= mms_runtime.MIN_PYTHON
    assert mms_runtime.ensure_supported_python("MMS") is None


def test_runtime_candidate_list_prefers_explicit_python(monkeypatch):
    import mms_runtime

    monkeypatch.setenv("MMS_PYTHON", "/tmp/custom-python")

    candidates = mms_runtime._candidate_pythons()

    assert candidates[0] == "/tmp/custom-python"
    assert "python3.11" in candidates
