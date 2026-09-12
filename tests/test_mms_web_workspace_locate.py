"""A dropped folder arrives as a bare name; the service has to find it on disk."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from mms_web.errors import WebError
from mms_web.workspace_search import locate_folder, search_workspaces


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """No zoxide, no Spotlight: only the sources the test sets up."""
    monkeypatch.setattr('mms_web.workspace_search.shutil.which', lambda _: None)
    monkeypatch.setattr('mms_web.workspace_search.os.access', lambda *_: False)
    monkeypatch.setattr('mms_web.workspace_search._spotlight_directories', lambda *_: ([], True))
    monkeypatch.setattr('mms_web.workspace_search.real_home', lambda: tmp_path.resolve())


def _catalog(*paths):
    return SimpleNamespace(_workspaces=lambda: [
        {'id': f'w{i}', 'name': Path(p).name, 'path': str(p)} for i, p in enumerate(paths)])


def test_folder_beside_a_known_workspace_resolves_without_the_picker(tmp_path):
    projects = tmp_path / 'projects'
    (projects / 'runtimia').mkdir(parents=True)
    dropped = projects / 'tts'
    (dropped / 'voices').mkdir(parents=True)
    (dropped / 'README.md').write_text('hi')
    result = locate_folder(_catalog(projects / 'runtimia'), {'name': 'tts', 'children': ['voices', 'README.md']})
    assert result['sure'] is True
    assert result['matches'][0]['path'] == str(dropped.resolve())


def test_contents_pick_the_right_folder_when_the_name_repeats(tmp_path):
    for parent, children in (('one', ['x']), ('two', ['voices', 'README.md'])):
        for child in children:
            (tmp_path / parent / 'tts' / child).mkdir(parents=True)
    result = locate_folder(_catalog(), {'name': 'tts', 'children': ['voices', 'README.md']})
    assert result['sure'] is True
    assert result['matches'][0]['path'] == str((tmp_path / 'two' / 'tts').resolve())
    assert len(result['matches']) == 2


def test_a_folder_nested_in_a_known_workspace_is_found_even_under_a_dot_directory(tmp_path):
    nested = tmp_path / 'repo' / '.worktrees' / 'task' / 'apps' / 'mms-web'
    (nested / 'src').mkdir(parents=True)
    result = locate_folder(_catalog(tmp_path / 'repo'), {'name': 'mms-web', 'children': ['src']})
    assert result['sure'] is True
    assert result['matches'][0]['path'] == str(nested.resolve())


def test_ambiguous_folders_are_offered_instead_of_guessed(tmp_path):
    for parent in ('one', 'two'):
        (tmp_path / parent / 'tts').mkdir(parents=True)
    result = locate_folder(_catalog(), {'name': 'tts', 'children': []})
    assert result['sure'] is False
    assert len(result['matches']) == 2
    missing = locate_folder(_catalog(), {'name': 'absent-folder', 'children': []})
    assert missing == {'matches': [], 'sure': False}


@pytest.mark.parametrize('children', [[], ['README.md', 'expected-file.txt']])
def test_single_partial_or_missing_fingerprint_needs_a_choice(tmp_path, children):
    folder = tmp_path / 'tts'
    folder.mkdir()
    (folder / 'README.md').touch()
    result = locate_folder(_catalog(folder), {'name': 'tts', 'children': children})
    assert result['matches']
    assert result['sure'] is False


def test_known_candidate_does_not_hide_a_better_match_in_another_root(tmp_path):
    first = tmp_path / 'first' / 'tts'
    second = tmp_path / 'second' / 'nested' / 'tts'
    for folder in (first, second):
        folder.mkdir(parents=True)
        (folder / 'README.md').touch()
    (second / 'expected-file.txt').touch()
    result = locate_folder(_catalog(first, tmp_path / 'second'),
                           {'name': 'tts', 'children': ['README.md', 'expected-file.txt']})
    assert len(result['matches']) == 2
    assert result['matches'][0]['path'] == str(second.resolve())
    assert result['sure'] is True


def test_same_fingerprint_in_two_scan_roots_stays_ambiguous(tmp_path):
    roots = [tmp_path / 'first', tmp_path / 'second']
    for root in roots:
        folder = root / 'nested' / 'tts'
        folder.mkdir(parents=True)
        (folder / 'README.md').touch()
    result = locate_folder(_catalog(*roots), {'name': 'tts', 'children': ['README.md']})
    assert len(result['matches']) == 2
    assert result['sure'] is False


def test_a_folder_name_can_never_carry_a_path(tmp_path):
    for name in ('', '..', 'a/b', 'bad\x00name', 'x' * 201):
        with pytest.raises(WebError):
            locate_folder(_catalog(), {'name': name})


def test_search_falls_back_to_the_system_index_when_nothing_is_familiar(tmp_path, monkeypatch):
    folder = tmp_path / 'deep' / 'nested' / 'tts'
    folder.mkdir(parents=True)
    monkeypatch.setattr('mms_web.workspace_search._spotlight_directories',
                        lambda name, home: ([folder, tmp_path / 'gone'], True))
    rows = search_workspaces(_catalog(), {'query': 'tts'})['workspaces']
    assert [row['path'] for row in rows] == [str(folder.resolve())]
    assert search_workspaces(_catalog(), {'query': ''})['workspaces'] == []


def test_a_search_that_ran_out_of_budget_never_skips_the_picker(tmp_path, monkeypatch):
    """A sweep that stopped early may simply not have reached the real folder.

    Everything else about the match can look perfect — one candidate, every
    dropped entry present — and still be the wrong directory, because the one
    that was dropped was never visited. Adopting it silently moves where the
    session works.
    """
    projects = tmp_path / 'projects'
    (projects / 'runtimia').mkdir(parents=True)
    dropped = projects / 'tts'
    (dropped / 'voices').mkdir(parents=True)
    payload = {'name': 'tts', 'children': ['voices']}

    assert locate_folder(_catalog(projects / 'runtimia'), payload)['sure'] is True

    monkeypatch.setattr('mms_web.workspace_search._scan_directories',
                        lambda name, plans: ([dropped], False))
    result = locate_folder(_catalog(projects / 'runtimia'), payload)
    assert result['sure'] is False
    # The candidate is still offered; only the certainty is withdrawn.
    assert result['matches'][0]['path'] == str(dropped.resolve())


def test_a_truncated_index_answer_also_withdraws_certainty(tmp_path, monkeypatch):
    projects = tmp_path / 'projects'
    (projects / 'runtimia').mkdir(parents=True)
    dropped = projects / 'tts'
    (dropped / 'voices').mkdir(parents=True)
    payload = {'name': 'tts', 'children': ['voices']}

    monkeypatch.setattr('mms_web.workspace_search._spotlight_directories',
                        lambda *_: ([], False))
    assert locate_folder(_catalog(projects / 'runtimia'), payload)['sure'] is False


def test_the_sweep_reports_whether_it_finished(tmp_path, monkeypatch):
    from mms_web.workspace_search import _scan_directories

    root = tmp_path / 'root'
    (root / 'a' / 'tts').mkdir(parents=True)
    found, complete = _scan_directories('tts', [(root, 4)])
    assert [path.name for path in found] == ['tts']
    assert complete is True

    # Out of budget with directories still queued.
    monkeypatch.setattr('mms_web.workspace_search._SCAN_BUDGET', 1)
    found, complete = _scan_directories('tts', [(root, 4)])
    assert complete is False

    # Out of plans is not the same as out of budget.
    monkeypatch.setattr('mms_web.workspace_search._SCAN_BUDGET', 8000)
    _, complete = _scan_directories('tts', [])
    assert complete is True


def test_a_folder_drop_does_not_freeze_every_other_request(tmp_path, monkeypatch):
    """Finding a dropped folder sweeps the disk; the rest of Pilot must go on.

    These sweeps run for seconds. Held under the mutation lock, a single drop
    stopped sending a message, stopping a session and confirming an update for
    as long as it took.
    """
    import threading
    from unittest.mock import patch

    from mms_web.server import WebApplication

    with patch("mms_web.server._adapter", return_value=None):
        app = WebApplication(state_root=tmp_path / "state")
    app.catalog = _catalog()
    try:
        started = threading.Event()
        release = threading.Event()

        def slow_sweep(name, plans):
            started.set()
            release.wait(timeout=10)
            return [], True

        monkeypatch.setattr("mms_web.workspace_search._scan_directories", slow_sweep)
        monkeypatch.setattr("mms_web.workspace_search._spotlight_directories", lambda *_: ([], True))
        monkeypatch.setattr("mms_web.workspace_search.shutil.which", lambda _: None)
        monkeypatch.setattr("mms_web.workspace_search.os.access", lambda *_: False)

        drop = threading.Thread(
            target=lambda: app.post(["workspaces", "locate"], {"name": "tts", "children": ["x"]}),
            daemon=True,
        )
        drop.start()
        assert started.wait(timeout=5), "the sweep never started"

        # While it runs, the lock must be free for anything else.
        assert app.mutation_lock.acquire(timeout=2), "a folder drop is holding the mutation lock"
        app.mutation_lock.release()
        release.set()
        drop.join(timeout=5)
    finally:
        app.close()
