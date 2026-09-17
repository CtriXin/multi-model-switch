"""An in-page update replaces the installation too, or says why it cannot (#193)."""
import json
import re
import shutil
from pathlib import Path

import pytest

from mms_web.update_install import DIRECTORIES, FILES, GLOBS, describe, install, manifest
from mms_web.updates import upgrade_notice

ROOT = Path(__file__).resolve().parents[1]


def _release(root: Path, *, version: str) -> Path:
    """A staged source shaped like the release tarball, only smaller."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "mms").write_text(f"#!/usr/bin/env python3\n# {version}\n")
    (root / "mmf").write_text(f"#!/bin/sh\n# {version}\n")
    (root / "mms_core.py").write_text(f'VERSION_MARK = "{version}"\n')
    (root / "mms_version.py").write_text(f'VERSION = "{version}"\n')
    (root / "mms_web").mkdir()
    (root / "mms_web" / "__main__.py").write_text(f"# {version}\n")
    (root / "config").mkdir()
    (root / "config" / "provider-profiles.json").write_text("{}\n")
    return root


def test_the_manifest_covers_everything_install_sh_copies():
    """The two copy lists have to agree, or an update leaves files behind."""
    copied = set()
    for line in (ROOT / "install.sh").read_text(encoding="utf-8").splitlines():
        # Only statements that put a source path into the installation count;
        # the installer also reads templates it never copies.
        if "$MMS_HOME" not in line or not re.search(r"\b(cp|copy_dir_safely|copy_hooks_dir_safely)\b", line):
            continue
        # Both spellings the installer uses, including paths with a space.
        for pattern in (r'"\$SOURCE_DIR/([^"]+)"', r'"\$SOURCE_DIR"/(\S+)'):
            for match in re.finditer(pattern, line):
                copied.add(match.group(1).strip('"'))
    assert copied, "install.sh copy statements are no longer recognisable"
    known = set(FILES) | set(DIRECTORIES)
    for name in sorted(copied):
        if name in known or name in {n.split("/")[0] for n in known}:
            continue
        if any(Path(name).match(pattern) for pattern in GLOBS):
            continue
        pytest.fail(f"install.sh copies {name!r} into the installation but update_install does not")


def test_manifest_lists_only_what_the_release_actually_has(tmp_path):
    names = manifest(_release(tmp_path / "candidate", version="9.9.9"))
    assert names == ["config", "mmf", "mms", "mms_core.py", "mms_version.py", "mms_web"]
    assert "vendor" not in names and "MMS Pilot.command" not in names


def test_a_source_checkout_is_never_written_to(tmp_path):
    checkout = tmp_path / "repo"
    (checkout / ".git").mkdir(parents=True)
    verdict = describe(checkout)
    assert verdict["updatesCli"] is False
    assert "源码检出" in verdict["reason"]
    # A directory nested inside a checkout is still the checkout.
    nested = checkout / "worktrees" / "issue-1"
    nested.mkdir(parents=True)
    assert describe(nested)["updatesCli"] is False


def test_a_real_installation_is_installable(tmp_path):
    verdict = describe(_release(tmp_path / "installed", version="1.0.0"))
    assert verdict["updatesCli"] is True and verdict["reason"] == ""


def test_install_replaces_the_installation_and_keeps_local_state(tmp_path):
    installed = _release(tmp_path / "installed", version="1.0.0")
    # Local state the release does not carry must survive the update.
    (installed / ".venv").mkdir()
    (installed / ".venv" / "pyvenv.cfg").write_text("home = /usr\n")
    (installed / "logs").mkdir()
    (installed / "logs" / "mms-web.log").write_text("old log\n")
    candidate = _release(tmp_path / "candidate", version="2.0.0")
    (candidate / "mmslogs").write_text("#!/bin/sh\n# 2.0.0\n")

    names = install(candidate, installed, tmp_path / "backup")

    assert "mmslogs" in names
    assert 'VERSION = "2.0.0"' in (installed / "mms_version.py").read_text()
    assert "# 2.0.0" in (installed / "mms_web" / "__main__.py").read_text()
    assert (installed / "mmslogs").is_file()
    assert (installed / ".venv" / "pyvenv.cfg").read_text() == "home = /usr\n"
    assert (installed / "logs" / "mms-web.log").read_text() == "old log\n"
    assert not list(installed.glob("*.mms-update-new"))
    assert 'VERSION = "1.0.0"' in (tmp_path / "backup" / "mms_version.py").read_text()


def test_a_failed_install_puts_the_previous_version_back(tmp_path, monkeypatch):
    installed = _release(tmp_path / "installed", version="1.0.0")
    candidate = _release(tmp_path / "candidate", version="2.0.0")
    real_copytree = shutil.copytree
    calls = {"n": 0}

    def explode(source, target, **kwargs):
        # Fail on the directory, after the plain files have been replaced.
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("disk full")
        return real_copytree(source, target, **kwargs)

    monkeypatch.setattr("mms_web.update_install.shutil.copytree", explode)
    with pytest.raises(OSError):
        install(candidate, installed, tmp_path / "backup")

    # Every replaced path is back at the version that was serving.
    assert 'VERSION = "1.0.0"' in (installed / "mms_version.py").read_text()
    assert "# 1.0.0" in (installed / "mms_web" / "__main__.py").read_text()
    assert (installed / "mms").read_text().endswith("# 1.0.0\n")
    assert not list(installed.glob("*.mms-update-new"))


def test_an_added_path_is_removed_again_when_the_install_fails(tmp_path, monkeypatch):
    installed = _release(tmp_path / "installed", version="1.0.0")
    candidate = _release(tmp_path / "candidate", version="2.0.0")
    (candidate / "mmslogs").write_text("new file\n")
    real_copy = shutil.copy2

    def explode(source, target, **kwargs):
        if Path(source).name == "mms_version.py":
            raise OSError("disk full")
        return real_copy(source, target, **kwargs)

    monkeypatch.setattr("mms_web.update_install.shutil.copy2", explode)
    with pytest.raises(OSError):
        install(candidate, installed, tmp_path / "backup")
    assert not (installed / "mmslogs").exists()


def test_the_upgrade_notice_is_the_release_section_and_nothing_else():
    body = """# v4.15.0 标题

- 平常的条目

## 升级须知

- 端口从 8766 回到 8765
- `mmd` 不再可用

### 细节

仍属于须知。

## 其它变化

不该出现。
"""
    notice = upgrade_notice(body)
    assert "端口从 8766 回到 8765" in notice
    assert "仍属于须知" in notice
    assert "不该出现" not in notice
    assert "平常的条目" not in notice
    # A release without the section declares no cost, which is not an error.
    assert upgrade_notice("# v4.15.0\n\n- 只有普通条目\n") == ""
    assert upgrade_notice(None) == ""


def _spec(tmp_path, *, old_source: Path, staged: Path) -> dict:
    state = tmp_path / "state"
    (state / "updates").mkdir(parents=True, exist_ok=True)
    operation_root = state / "updates" / "operations" / "op-1"
    operation_root.mkdir(parents=True)
    return {"state": str(state), "source": str(staged), "oldSource": str(old_source),
            "target": "v2.0.0", "armed": str(operation_root / "armed")}


def test_a_verified_update_replaces_the_installation_and_drops_the_pointer(tmp_path):
    """With the installation on the new version, the staged copy is not needed."""
    from mms_web.update_handoff import install_alongside

    installed = _release(tmp_path / "installed", version="1.0.0")
    staged = _release(tmp_path / "staged", version="2.0.0")
    spec = _spec(tmp_path, old_source=installed, staged=staged)

    assert install_alongside(spec) is True
    assert 'VERSION = "2.0.0"' in (installed / "mms_version.py").read_text()
    report = json.loads((Path(spec["armed"]).parent / "installation.json").read_text())
    assert report["installed"] is True and report["root"] == str(installed)


def test_a_checkout_keeps_serving_from_the_staged_copy(tmp_path):
    """Refusing to touch a worktree must not cost the user the update."""
    from mms_web.update_handoff import install_alongside

    checkout = _release(tmp_path / "repo", version="1.0.0")
    (checkout / ".git").mkdir()
    staged = _release(tmp_path / "staged", version="2.0.0")
    spec = _spec(tmp_path, old_source=checkout, staged=staged)

    assert install_alongside(spec) is False
    assert 'VERSION = "1.0.0"' in (checkout / "mms_version.py").read_text()
    report = json.loads((Path(spec["armed"]).parent / "installation.json").read_text())
    assert report["installed"] is False and "源码检出" in report["reason"]


def test_a_failed_installation_is_reported_and_not_claimed(tmp_path, monkeypatch):
    from mms_web.update_handoff import install_alongside

    installed = _release(tmp_path / "installed", version="1.0.0")
    staged = _release(tmp_path / "staged", version="2.0.0")
    spec = _spec(tmp_path, old_source=installed, staged=staged)
    monkeypatch.setattr("mms_web.update_install.manifest", lambda _source: [])

    assert install_alongside(spec) is False
    report = json.loads((Path(spec["armed"]).parent / "installation.json").read_text())
    assert report["installed"] is False and "ValueError" in report["reason"]


def test_a_staged_copy_from_an_earlier_update_is_not_an_installation(tmp_path):
    """A Pilot updated before #195 serves from `<state>/updates/versions/...`.

    Installing into that directory would remove the pointer and leave the next
    start falling back to the older source the launcher points at, so the web
    app would silently move backwards.
    """
    staged = _release(tmp_path / "state" / "updates" / "versions" / "v4.15.0-abcd" / "source",
                      version="4.15.0")
    verdict = describe(staged)
    assert verdict["updatesCli"] is False
    assert "暂存副本" in verdict["reason"]


def test_a_staged_copy_keeps_the_pointer_instead_of_being_overwritten(tmp_path):
    from mms_web.update_handoff import install_alongside

    staged_old = _release(tmp_path / "state" / "updates" / "versions" / "v1.0.0-aaaa" / "source",
                          version="1.0.0")
    staged_new = _release(tmp_path / "staged", version="2.0.0")
    spec = _spec(tmp_path, old_source=staged_old, staged=staged_new)

    assert install_alongside(spec) is False
    assert 'VERSION = "1.0.0"' in (staged_old / "mms_version.py").read_text()


def test_promotion_failure_restores_the_file_already_moved_to_backup(tmp_path, monkeypatch):
    installed = _release(tmp_path / 'installed', version='1.0.0')
    candidate = _release(tmp_path / 'candidate', version='2.0.0')
    rename = Path.rename

    def fail_promotion(path, target):
        if path.name == 'mms_version.py.mms-update-new':
            raise OSError('promotion failed')
        return rename(path, target)

    monkeypatch.setattr(Path, 'rename', fail_promotion)
    with pytest.raises(OSError, match='promotion failed'):
        install(candidate, installed, tmp_path / 'backup')
    assert 'VERSION = "1.0.0"' in (installed / 'mms_version.py').read_text()
    assert (installed / 'mms').read_text().endswith('# 1.0.0\n')


def _verified_candidate(tmp_path, monkeypatch, *, prerelease=None):
    from mms_web import server
    from mms_web.runtime import private_json
    from mms_web.update_handoff import install_alongside
    monkeypatch.setattr(server, '_adapter', lambda *a, **kw: None)
    app = server.WebApplication(state_root=tmp_path / 'state', config_root=tmp_path / 'config-root')
    app.probation_token = 'verified-token'
    app.maintenance = True
    old = _release(tmp_path / 'installed', version='1.0.0')
    new = _release(tmp_path / 'staged', version=server.VERSION)
    spec = _spec(tmp_path, old_source=old, staged=new)
    spec['target'] = 'v' + server.VERSION
    # This is the OLD guardian contract: no metadata helper or prerelease flag.
    assert install_alongside(spec)
    operation = {'id': 'op-1', 'target': spec['target'], 'phase': 'restarting'}
    if prerelease is not None:
        operation['prerelease'] = prerelease
    private_json(app.state_root / 'updates/operation.json', operation)
    private_json(app.config_root / 'version.json', {'installed_ref': 'v1.0.0', 'installed_version': 'v1.0.0',
                 'install_channel': 'stable', 'preferred_language': 'en', 'custom': {'preserve': [1, 2]}})
    return app, old


@pytest.mark.parametrize('prerelease', [True, False])
def test_old_guardian_new_candidate_records_actual_release_and_preserves_preferences(tmp_path, monkeypatch, prerelease):
    from mms_web import updates
    from mms_web.server import VERSION
    from mms_web.runtime import private_json
    app, installed = _verified_candidate(tmp_path, monkeypatch)
    calls = []
    def release(tag):
        calls.append(tag)
        return {'prerelease': prerelease}
    monkeypatch.setattr(updates, 'fetch_tag_release', release)
    # Deliberately opposite preference; it must never classify the install.
    private_json(app.state_root / 'updates/settings.json', {'channel': 'stable' if prerelease else 'preview'})
    assert app.post(['update', 'commit'], {'token': 'verified-token'}) == {'ok': True}
    metadata = updates.read_json(app.config_root / 'version.json')
    assert calls == ['v' + VERSION]
    assert metadata['installed_ref'] == metadata['installed_version'] == 'v' + VERSION
    assert metadata['install_channel'] == ('preview' if prerelease else 'stable')
    assert metadata['release_track'] == ('dev' if prerelease else 'stable')
    assert metadata['release_track_version'] == VERSION
    assert metadata['release_track_label'] == VERSION.split('.')[0] + ('.x Preview' if prerelease else '.x Stable')
    assert metadata['preferred_language'] == 'en' and metadata['custom'] == {'preserve': [1, 2]}
    assert metadata['source'] == 'pilot-update'
    assert re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', metadata['installed_at'])
    assert f'VERSION = "{VERSION}"' in (installed / 'mms_version.py').read_text()
    operation = updates.read_json(app.state_root / 'updates/operation.json')
    assert operation['phase'] == 'complete' and not operation['metadataWarning']
    assert not app.maintenance and not app.probation_token


def test_frozen_prerelease_does_not_need_network_at_commit(tmp_path, monkeypatch):
    from mms_web import updates
    app, _ = _verified_candidate(tmp_path, monkeypatch, prerelease=True)
    monkeypatch.setattr(updates, 'fetch_tag_release', lambda tag: pytest.fail('frozen release must not refetch'))
    app.post(['update', 'commit'], {'token': 'verified-token'})
    assert updates.read_json(app.config_root / 'version.json')['install_channel'] == 'preview'


@pytest.mark.parametrize('failure', ['write', 'invalid-json', 'unknown-release'])
def test_metadata_failure_warns_but_commits_verified_source(tmp_path, monkeypatch, failure):
    from mms_web import runtime, updates
    from mms_web.server import VERSION
    app, installed = _verified_candidate(tmp_path, monkeypatch, prerelease=None if failure == 'unknown-release' else True)
    meta = app.config_root / 'version.json'
    if failure == 'invalid-json':
        meta.write_text('{broken')
    original = meta.read_bytes()
    writer = runtime.private_json
    def fail_metadata(path, value):
        if Path(path) == meta:
            raise OSError('read-only')
        return writer(path, value)
    if failure == 'write':
        monkeypatch.setattr(runtime, 'private_json', fail_metadata)
    if failure == 'unknown-release':
        monkeypatch.setattr(updates, 'fetch_tag_release', lambda tag: (_ for _ in ()).throw(OSError('offline')))
    assert app.post(['update', 'commit'], {'token': 'verified-token'}) == {'ok': True}
    operation = updates.read_json(app.state_root / 'updates/operation.json')
    assert operation['phase'] == 'complete'
    assert operation['metadataWarning'] and operation['metadataWarning'] in operation['message']
    assert meta.read_bytes() == original
    assert f'VERSION = "{VERSION}"' in (installed / 'mms_version.py').read_text()
    assert not app.maintenance


def test_staged_only_or_wrong_version_never_relabels_cli(tmp_path, monkeypatch):
    from mms_web import updates
    from mms_web.runtime import private_json
    from mms_web.update_install import record_committed_install
    from mms_web.server import VERSION
    app, _ = _verified_candidate(tmp_path, monkeypatch, prerelease=True)
    operation = updates.read_json(app.state_root / 'updates/operation.json')
    before = (app.config_root / 'version.json').read_bytes()
    receipt = app.state_root / 'updates/operations/op-1/installation.json'
    private_json(receipt, {'installed': False})
    assert record_committed_install(app.config_root, app.state_root, operation, VERSION) == ''
    private_json(receipt, {'installed': True, 'version': 'v1.0.0'})
    assert record_committed_install(app.config_root, app.state_root, operation, VERSION)
    assert (app.config_root / 'version.json').read_bytes() == before


def test_preview_metadata_displays_the_actual_installed_series(monkeypatch):
    from mms_core import _release_track_for_channel
    monkeypatch.delenv('MMS_COMMAND_NAME', raising=False)
    monkeypatch.delenv('MMS_PREVIEW_MODE', raising=False)
    result = _release_track_for_channel({'installed_ref': 'v5.1.0', 'install_channel': 'preview'})
    assert result == {'release_track': 'dev', 'release_track_series': '5.x',
                      'release_track_version': '5.1.0', 'release_track_label': '5.x Preview'}
