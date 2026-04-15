from mms_bridge import _AnthropicTranslator


def test_reasoning_prefix_hidden_when_summary_is_empty():
    translator = _AnthropicTranslator("gpt-5.4")

    translator.process("response.created", {})
    translator.process("response.output_item.added", {
        "item": {"type": "reasoning", "id": "reasoning-1"},
    })
    translator.process("response.content_part.added", {
        "item_id": "message-1",
        "part": {"type": "output_text"},
    })
    events = translator.process("response.output_text.delta", {
        "item_id": "message-1",
        "delta": "Hello",
    })

    text_event = next(event for event in events if event[0] == "content_block_delta")
    assert text_event[1]["delta"]["text"] == "Hello"


def test_reasoning_prefix_uses_summary_length_when_present():
    translator = _AnthropicTranslator("gpt-5.4")

    translator.process("response.created", {})
    translator.process("response.output_item.added", {
        "item": {"type": "reasoning", "id": "reasoning-1"},
    })
    translator.process("response.reasoning_summary_text.delta", {
        "item_id": "reasoning-1",
        "delta": "abc",
    })
    translator.process("response.content_part.added", {
        "item_id": "message-1",
        "part": {"type": "output_text"},
    })
    events = translator.process("response.output_text.delta", {
        "item_id": "message-1",
        "delta": "Hello",
    })

    text_event = next(event for event in events if event[0] == "content_block_delta")
    assert text_event[1]["delta"]["text"] == "[thinking: 3chars]\n\nHello"
