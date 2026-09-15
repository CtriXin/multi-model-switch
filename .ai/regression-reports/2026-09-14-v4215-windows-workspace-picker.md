# v4.21.5 Windows workspace picker regression

- timestamp: 2026-09-14 Asia/Singapore
- task/scope: Windows Native Preview workspace search and folder picker follow-up
- changed files: `mms_web/server.py`, `mms_web/workspace_search.py`, `mms_version.py`, workspace picker/search tests
- expected behavior: Windows can browse a local folder through the native picker; drive-letter and UNC paths are recognized; common folders such as Downloads are found from a bounded home-directory search.
- regression risk/blast radius: Windows workspace discovery and picker only; POSIX picker and existing catalog/zoxide/Spotlight paths remain unchanged.
- commands run: `PYTHONPATH=. uv run pytest -q tests/test_mms_web_windows_workspace_picker.py tests/test_mms_web_workspace_search.py tests/test_mms_web_workspace_locate.py`
- result: PASS (19 passed)
- known unrelated failures/skipped areas: Windows desktop native dialog and GitHub Windows Acceptance require the Windows host; not run locally.
- final status: source fix ready for commit and Windows acceptance.
