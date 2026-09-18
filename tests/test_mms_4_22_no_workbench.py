"""Assert 4.22.x line remains free of any Bot workbench modules, browser providers, or bot styles."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def test_no_bot_modules_in_4_22_line():
    """Verify that no bot backend, frontend or test modules exist on the 4.22 line."""
    assert not (ROOT / "mms_web/browser_provider.py").exists(), "mms_web/browser_provider.py should not exist in 4.22"

    bot_py = list((ROOT / "mms_web").glob("*bot*.py"))
    bot_tsx = list((ROOT / "apps/mms-web/src").glob("*[Bb]ot*.tsx"))
    bot_css = list((ROOT / "apps/mms-web/src").glob("*[Bb]ot*.css"))
    test_bot_py = list((ROOT / "tests").glob("*bot*.py"))

    assert bot_py == [], f"Found bot python modules: {bot_py}"
    assert bot_tsx == [], f"Found bot tsx modules: {bot_tsx}"
    assert bot_css == [], f"Found bot css modules: {bot_css}"
    assert test_bot_py == [], f"Found bot test modules: {test_bot_py}"


def test_settings_page_has_no_bot_symbols():
    """Verify SettingsPage.tsx does not contain 'bot' substring (case-insensitive)."""
    settings_src = (ROOT / "apps/mms-web/src/SettingsPage.tsx").read_text(encoding="utf-8")
    assert "bot" not in settings_src.lower(), f"Found 'bot' substring in SettingsPage.tsx"


def test_studio_css_has_no_bot_selectors():
    """Verify studio.css does not contain bot workspace or sidebar bot selectors."""
    studio_css = (ROOT / "apps/mms-web/src/studio.css").read_text(encoding="utf-8")
    matches = re.findall(r"\bbot\b|\.bot", studio_css, re.IGNORECASE)
    assert matches == [], f"Found bot selectors in studio.css: {matches}"
