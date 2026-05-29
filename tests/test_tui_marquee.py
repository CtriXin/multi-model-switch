from mms_tui import _display_width, _marquee_text


def test_marquee_text_scrolls_long_model_names():
    text = "anthropic/claude-opus-4.6-thinking"
    first = _marquee_text(text, 12, 0)
    later = _marquee_text(text, 12, 8)

    assert first == "anthropic/cl"
    assert later != first
    assert _display_width(first) <= 12
    assert _display_width(later) <= 12


def test_marquee_text_keeps_short_model_names_static():
    text = "mimo-v2.5"

    assert _marquee_text(text, 20, 0) == text
    assert _marquee_text(text, 20, 99) == text
