# Dev installer follow-up regression report

- Timestamp: 2026-09-15 Asia/Singapore
- Task/scope: Sync `dev` with the v4.21.14 Windows baseline and make preview installs honor `--launch-web`.
- Changed files: `install.sh`, `README.md`, `docs/mms-web/RELEASE-v4.21.14.md`, `mms_web_static/build.json`, and the v4.21.14 static assets.
- Expected behavior: `--channel dev --launch-web` starts Pilot after installation; dev reports the v4.21.14 baseline; update validation accepts the shipped Web bundle and local release notes.
- Regression risk/blast radius: installer post-install behavior and dev's bundled Web assets; config, credentials, sessions, and provider routing are untouched.
- Commands run: `python3 -m pytest -q tests/test_mms_web_update_transaction.py tests/test_mms_web_updates.py`; `git diff --check`.
- Result: PASS, 17 tests passed; whitespace check passed.
- Known unrelated failures/skipped areas: full CI remains the authoritative check; no provider/account smoke was run.
- Final status: local fix ready for CI.
