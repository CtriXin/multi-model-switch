from __future__ import annotations

import io


def test_encode_toon_table_array():
    from mms_session.toon import encode_toon

    payload = {
        "models": [
            {"id": "kimi-k2.5", "score": 91, "ok": True},
            {"id": "glm-4.6", "score": 88, "ok": False},
        ]
    }

    assert encode_toon(payload) == (
        "models[2]{id,score,ok}:\n"
        "  kimi-k2.5,91,true\n"
        "  glm-4.6,88,false"
    )


def test_choose_llm_data_format_uses_toon_only_when_smaller():
    from mms_session.toon import choose_llm_data_format

    repetitive = {
        "summaries": [
            {"model": f"model-{index}", "approach": "short plan", "next_step": "ship"}
            for index in range(8)
        ]
    }
    selected = choose_llm_data_format(repetitive)
    assert selected.format == "toon"
    assert selected.text.startswith("TOON:\n")
    assert selected.savings_chars > 0
    assert selected.toon_chars is not None
    assert selected.toon_chars < selected.json_chars

    tiny = {"ok": True}
    fallback = choose_llm_data_format(tiny)
    assert fallback.format == "json"
    assert fallback.text == '{\n  "ok": true\n}'


def test_choose_llm_data_format_falls_back_for_unsupported_shape():
    from mms_session.toon import choose_llm_data_format

    payload = {"rows": [{"a": 1}, {"b": 2}]}

    selected = choose_llm_data_format(payload)
    assert selected.format == "json"
    assert selected.toon_chars is None
    assert '"rows"' in selected.text


def test_mms_toon_cli_reads_json_from_stdin(monkeypatch, capsys):
    from mms_session.toon import main

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO('{"rows":[{"id":"a","ok":true},{"id":"b","ok":false}]}'),
    )

    assert main([]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.startswith("TOON:\n")
    assert "rows[2]{id,ok}:" in captured.out
    assert "  a,true" in captured.out
