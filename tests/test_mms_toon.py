from __future__ import annotations

import asyncio
import io


def test_encode_toon_table_array():
    from mms_toon import encode_toon

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
    from mms_toon import choose_llm_data_format

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
    from mms_toon import choose_llm_data_format

    payload = {"rows": [{"a": 1}, {"b": 2}]}

    selected = choose_llm_data_format(payload)
    assert selected.format == "json"
    assert selected.toon_chars is None
    assert '"rows"' in selected.text


def test_mms_toon_cli_reads_json_from_stdin(monkeypatch, capsys):
    from mms_toon import main

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


def test_phase3_synthesize_formats_structured_payload_as_toon(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path / "mms-config"))

    import mms_discuss

    captured = {}

    async def fake_stream_model(_client, _base_url, _api_key, _model, messages, max_tokens):
        captured["messages"] = messages
        captured["max_tokens"] = max_tokens
        yield "done"

    class FakeLive:
        def __init__(self, *_args, **_kwargs):
            self.renderables = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def update(self, renderable):
            self.renderables.append(renderable)

    monkeypatch.setattr(mms_discuss, "stream_model", fake_stream_model)
    monkeypatch.setattr(mms_discuss, "Live", FakeLive)

    summaries = {
        f"model-{index}": {
            "ok": True,
            "data": {
                "approach": "short plan",
                "reasoning": "because it is smaller",
                "risks": ["schema drift", "unknown model familiarity"],
                "key_decisions": ["fallback to JSON", "measure chars"],
                "next_step": "ship adapter",
            },
        }
        for index in range(8)
    }

    result = asyncio.run(
        mms_discuss.phase3_synthesize(
            {"base_url": "https://example.invalid", "api_key": "test"},
            object(),
            "judge-model",
            "compare structured payload formats",
            summaries,
        )
    )

    assert result == "done"
    assert captured["max_tokens"] == 1400
    user_message = captured["messages"][1]["content"]
    assert user_message.startswith("TOON:\n")
    assert "summaries:" in user_message
    assert "model-0:" in user_message
