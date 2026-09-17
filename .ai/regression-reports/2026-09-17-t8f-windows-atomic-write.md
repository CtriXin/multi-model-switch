# Regression Report · T8f Windows atomic write

- Timestamp: 2026-09-17 18:15 +08 (Asia/Singapore)
- Task/scope: Stride `4f269be35e274932` · packet `docs/mms-web/bot-work/T8f-windows-atomic-write-loses-data.md`
- Branch/base: `codex/stride-4f269be35e274932` ← `origin/main` `8a52a2da`
- Worktree: `/Users/xin/.local/share/stride/tasks/4f269be35e274932/workspace`
- PR: https://github.com/CtriXin/multi-model-switch/pull/318 (base `main`, not merged)

## Changed files

```
mms_web/runtime.py                         private_json retry + keep temp until exhausted
mms_web/updates.py                         check() outer except, thread logging, in-memory error
mms_web/sessions.py                        persist() logs then re-raises
tests/test_mms_web_atomic_write.py         6 tests (packet 1–5 + persist log)
.github/workflows/windows-acceptance.yml   run the new tests on windows-2022/2025
scripts/regression_fresh_user_gate.py      add the new test file to the full pytest list
```

## Expected behavior

- `os.replace` `PermissionError` / Windows winerror 5 or 32 is retried 10/20/40/80/160ms (~310ms), temp file kept until retries end, then raise. Destination is only ever reached via `os.replace`.
- Exhausted retries leave the existing destination JSON untouched and delete leftover `.web-*.tmp`.
- `UpdateService.check(manual=True)` does not raise to the caller when `private_json` fails; `status()["error"]` is nonempty (disk and/or in-memory).
- `request_check` / scheduler threads log unexpected exceptions.
- `session.persist()` logs the session id then re-raises (HTTP 500 on the request path). No new frontend banner.

## Regression risk / blast radius

- Every Web persistence path goes through `private_json`. Retry adds ≤310ms only on transient Windows replace failures; POSIX success path is still one `os.replace`.
- `check()` now swallows more exceptions than the inner fetch `except` did. That is the point: a daemon thread must not die silent. Fetch failures still write the same user-facing error string.
- `persist()` still raises, so `_runtime_view_locked` still surfaces a 500 rather than a stale cache. Catching `WebError` there is unchanged.
- No frontend / bundle rebuild. Protected launcher files untouched. No writes to real `~/.config/mms*`. No use of ports 8765/8766/8767/60824 by this task.

## Commands run

| 命令 | 结果 |
| --- | --- |
| `python3 -m pytest -q tests/test_mms_web_atomic_write.py` | **6 passed** |
| mutation 1 去掉重试循环 → test 重试成功 | **红** |
| mutation 2 耗尽后 `return` → test 重试耗尽 | **红** |
| mutation 3 外层 except 再抛 → test check 不再静默 | **红** |
| mutation 4 失败立刻 unlink 临时文件 → test 临时文件在每次 replace 时仍在 | **红** |
| 定向相关套件（sessions/updates/btw/message-control 等）origin/main | **244 passed** |
| 同上 + 新文件，head | **250 passed** |
| `python3 scripts/ci_pytest_regression.py --base origin/main` | base **63 failing of 2528**；head **63 failing of 2534**；无 base-pass/head-fail |
| `python3 scripts/regression_fresh_user_gate.py` 完整 | channel-switch **KeyError: 'runAt'**（5.0.6 peer，既有漂移） |
| 该 gate 在 channel-switch 之后的 pytest 列表 + NSR hook matrix | NSR **PASS**；**717 passed** |
| GitHub Windows Acceptance 4 cells | **全绿**（windows-2022 5.1/pwsh7，windows-2025 5.1/pwsh7+pi） |
| GitHub pytest / redline / digger | **绿** |

## Known unrelated failures / skipped

- `regression_fresh_user_gate.py` channel-switch：newer line 5.0.6 `create_task` 不再返回 `runAt`。T8a PR 已记录同类失败。本包未改 bots/schedule。
- **未在用户桌面 Windows + Defender 真机上点「检查更新」**。Windows CI 是 GitHub-hosted Server 镜像，跑了带 patch 的 `os.replace` 测试，不是 Defender 持有句柄的现场。
- 未做 `ConnectionAbortedError` 日志降级（packet 低优先，要求单独 commit）。
- 未重建 `mms_web_static/`。

## Final status

Fix landed on `codex/stride-4f269be35e274932` (`49801426`) and PR #318 against `main`. Not merged. Ready for committee; ship promptly after merge, then backflow `dev`.
