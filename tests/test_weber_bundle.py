"""Weber ships as one skill with its backends inside; sessions must see the same copy."""
import filecmp
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "weber"
BUNDLED = ROOT / "assets" / "session-assets" / "skills" / "weber"


def _same_tree(a: Path, b: Path) -> bool:
    comparison = filecmp.dircmp(a, b)
    if comparison.left_only or comparison.right_only or comparison.diff_files:
        return False
    return all(_same_tree(a / name, b / name) for name in comparison.common_dirs)


def test_bundled_weber_matches_vendor_copy():
    # The launcher prefers the assets copy; a vendor-only edit would never reach a session.
    assert _same_tree(VENDOR, BUNDLED)


def test_weber_routes_ego_first_and_keeps_backends_inside():
    text = (VENDOR / "SKILL.md").read_text(encoding="utf-8")
    routing = text[text.index("## Default Routing"):text.index("## Execution Loop")]
    first_row = next(line for line in routing.splitlines() if line.startswith("| ") and "`" in line and "Need" not in line)
    assert "ego-browser" in first_row
    assert "WEB_ACCESS_SKILL_DIR" in text and "backends-web-access" in text and "backends-agent-browser" in text
    assert "~/.codex/skills/web-access" not in text
    for backend in ("backends-web-access", "backends-agent-browser"):
        assert (VENDOR / backend / "SKILL.md").is_file()


def test_launcher_exports_weber_backend_dirs_without_overriding_explicit_env(monkeypatch, tmp_path):
    import mms_launchers

    weber = tmp_path / "weber"
    web_access = weber / "backends-web-access"
    agent_browser = weber / "backends-agent-browser"
    for path in (weber, web_access, agent_browser):
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text("# x\n", encoding="utf-8")
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: str(weber))
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: str(web_access))
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: str(agent_browser))

    env = mms_launchers._inject_weber_backend_hints({"WEB_ACCESS_SKILL_DIR": "/explicit/web-access"})

    assert env["WEBER_SKILL_DIR"] == str(weber)
    assert env["AGENT_BROWSER_SKILL_DIR"] == str(agent_browser)
    assert env["WEB_ACCESS_SKILL_DIR"] == "/explicit/web-access"


def test_real_home_hints_carry_weber_backend_dirs(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(tmp_path))
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_inject_rescue_launch_env", lambda env: env)
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: str(tmp_path / "weber"))
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")

    env = mms_launchers._inject_real_home_hints({})

    assert env["WEB_ACCESS_HOST_HOME"] == str(tmp_path)
    assert env["WEBER_SKILL_DIR"] == str(tmp_path / "weber")
    assert "WEB_ACCESS_SKILL_DIR" not in env
