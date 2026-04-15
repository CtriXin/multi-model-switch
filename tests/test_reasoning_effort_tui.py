from mms_tui import _EFFORT_OPTIONS, select_reasoning_effort_tui


def test_reasoning_effort_options_include_xhigh():
    values = [value for value, _label in _EFFORT_OPTIONS]
    assert values == ["low", "medium", "high", "xhigh"]


def test_reasoning_effort_tui_defaults_to_high():
    assert select_reasoning_effort_tui.__defaults__ == ("high",)
