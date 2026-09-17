# T8c — pytest 基线分类报告（第一阶段：只诊断，不改代码)

**任务来源**: `T8c-clean-the-pytest-baseline.md`(commit `1b710ef0`,branch `origin/dev`)
**实测基线**: `main` tip `a0f77398`(packet 在 `f663db83` 测的 63 个;两个 commit 之间只有 release/changelog 改动,见下文"和 packet 的 63 对账")
**复现命令**(与 packet 一致):

```bash
env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME \
  python3 -m pytest tests/ -q -p no:randomly
```

## 结论(先说结果)

- **65 个失败,10 个根因,0 个确认的 B 类(真 bug),1 个 B 类候选待裁决。** C 类(过期断言/测试没跟上有意行为变更)59 个,D 类(测试自身问题)6 个,A 类(环境依赖→skipif)0 个。
- **失败集合完全稳定**: 两次全量跑(run1 539s / run2 494s)失败清单逐条 diff 完全一致,无运行间波动。但有 **3 条是环境变量敏感的**(R9),换一台 shell 环境不同的机器数量会变——packet 作者数的 63 就是这么来的(对账见文末)。
- **packet 的核心判断成立**: `test_opencode_launcher.py` 的 37 个失败 = 2 个根因(32 个同享"capability bundle fail-closed",5 个同享"~/.config/mms 根退役"),不是 37 个问题。
- **`ci_pytest_regression.py` 的行为描述核对无误**(见末节),但发现它 `_clean_env()` 漏掉了三个会污染基线的环境变量,这是本报告新发现。
- 全部修完后基线预估: **0 failed, 2490 passed, 36 skipped**(65 个全部回到 passed;没有需要转成 skip 的 A 类)。

## 分类总表(按根因归组)

| 组 | 类 | 覆盖测试数 | 根因(一句话) | 建议动作 |
|---|---|---|---|---|
| R1 | C | 35 | `mms_config_root_mode()` 恒返回 `"preview"`(ed4b07ec 单 config root 化)+ preview 根缺 latest-approved bundle 时 fail-closed 抛 `CapabilityBundleError`,而测试 fixture 不写 bundle | 测试侧补 bundle fixture 或 mock resolver;详见 R1 |
| R2 | C | 7 | `mms_pi_support.py:1374` 起强制要求 runtime 显式声明 `protocols`(a672ed49),`test_pi_committee.py` 的 MODELS fixture 只有 base URL 没有 `protocols` | fixture 每条补 `protocols` 字段 |
| R3 | C | 10 | `~/.config/mms` 根退役(ed4b07ec / 33fd11fc),fixture 仍往退役根写数据或断言 stable 语义 | fixture 路径改 `mms-next`;断言改 preview 语义 |
| R4 | C | 2 | `main()` 默认路径改为从 v2 bundle bootstrap + preview 根跳过 startup routes export(3aae0748),测试还在 monkeypatch 旧入口 | 按新流程重写这两个测试 |
| R5 | C | 1 | cf914bec 给 capability facts 加了 `lru_cache`,测试篡改 payload 文件后没清缓存,等不到 fail-closed | 测试加 `clear_capability_resolver_caches()` |
| R6 | D | 2 | `docs/reference/model-capability-calibration/` 从 1 个 JSON 长到 6 个,测试的隐含前提(单文件)失效 | 见 R6,其中一条牵出 B 类候选 |
| R7 | C | 2 | `_claude_route_status_paths` 新增 `gateway_home` 关键字参数(per-PID 会话隔离),测试的替身 lambda 没跟上签名 | 替身 lambda 加 `**_kwargs` |
| R8 | C | 2 | PostCompact hook(f239cbba)与 web-access session skill overlay(9ab22bec)被有意退役/改为 no-op | 删除/更新过期断言 |
| R9 | D | 3 | 测试不隔离环境变量: `MMS_COMMAND_NAME`、`MMS_PI_SKILLS_OVERLAY`、conftest 注入的 `XDG_CONFIG_HOME` | 测试内 `delenv`;另见末节对 gate 脚本的建议 |
| R10 | D | 1 | `mms_core.main()` 会按 locale env 调 `set_language()` 且 monkeypatch 不还原模块级语言状态,后置测试断言的中文 label 变成英文 | 见 R10(测试间污染,packet 点名最值得修的一类) |

**类合计: A=0,B=0(1 候选),C=59,D=6。**

---

## R1 — capability bundle fail-closed(35 个,C)

**覆盖**: `test_opencode_launcher.py` 32 个(除 R3 的 5 个迁移测试外的全部)+ `test_model_name_exports.py::test_get_export_env_includes_mms_model_name_for_standard_runners` + `test_config_web.py` 2 个。

**证据链**(以 `test_opencode_config_uses_openai_compatible_provider` 为例,run1 traceback):

```
mms_opencode_config.py:927 opencode_model_config
→ mms_opencode_config.py:475 opencode_model_capabilities
→ mms_capability_resolver.py:253 resolve_model_capabilities
→ mms_capability_resolver.py:147 CapabilityBundleError:
  "latest-approved capabilities unavailable for selected config root:
   .../mms-test-xdg-*/mms-next/generated/model-registry.latest-approved.json"
```

机制: ed4b07ec 之后 `mms_state_io.mms_config_root_mode()` 无条件返回 `"preview"`(源码注释: "the mode is always preview");`mms_capability_resolver._load_default_approved_facts_shared()` 对 preview 根缺 bundle 时按模块 docstring 的设计意图 fail-closed("Explicitly selected preview roots must not silently continue")。conftest 把 `XDG_CONFIG_HOME` 指到空临时目录,`generated/model-registry.latest-approved.json` 不存在 → 抛错。

`test_config_web.py` 两条(`..._are_profile_backed_not_hardcoded`、`..._returns_policy_capabilities`)是同一根因的哑火版: `mms_config_web._model_capability_defaults` 用 `except Exception: pass` 吞掉异常,capability 落回保守默认,`reasoning` 变 `False`。这两个测试在 5ed9c5b4 引入时代码逻辑与现在逐字相同,当时能过是因为 stable 根还能回退到 provider profiles。

**建议动作**: 不是 skipif——这是 C 类。给这批测试一个共享 fixture,在临时 config root 里写一份最小 latest-approved bundle(仓库里已有现成写法: `tests/test_registry_runtime_resolver.py::_write_bundle`),或 monkeypatch `mms_capability_resolver._load_default_approved_facts_shared`(test_mimo_1m_context.py:163 已有先例)。

**需要人裁决的边界**: fail-closed 对"全新 preview 根、还没发过 bundle"的真实安装也生效。真机上 `~/.config/mms-next/generated/` 有 bundle(已核实存在),所以正常安装不触发;但"首次启动尚未 publish bundle 时 opencode 启动链路是否会撞到"这一点建议产品侧确认,不属于本阶段改动范围。

## R2 — Pi 强制显式 protocol 声明(7 个,C)

**覆盖**: `test_pi_committee.py` 全部 7 个。

**证据**: 错误统一为 `RuntimeError: Pi runtime requires a declared protocol with its matching base URL`(mms_pi_support.py:1374)。a672ed49 "fix(pi): honor declared protocol transports" 引入 `_pi_declared_protocols()` 只认 runtime 里显式的 `protocols` 字段;而 `test_pi_committee.py` 的 `MODELS` fixture(第 23 行起)每条只有 `anthropic_base_url` / `openai_base_url`,没有 `protocols` → `_pi_protocol_variants()` 返回空 → 抛错。

注: `test_model_backup_runs_after_primary_failure` 在我机器上的报错文本还叠加了 R9 的 `MMS_PI_SKILLS_OVERLAY` 泄漏(argv 里多了 `--no-skills --skill <我本机 overlay 路径>`),但主因是 CommitteeError;scrub 掉该环境变量后仍因 R2 失败(已实测)。

**建议动作**: fixture 每条按 base URL 补 `protocols`(如 `["anthropic_messages"]`)。改完这 7 个应全部回绿。

## R3 — `~/.config/mms` 退役,fixture/断言还在旧世界(10 个,C)

**覆盖与证据**:

| 测试 | 证据 |
|---|---|
| `test_opencode_launcher.py` 5 个迁移测试(`migrates_existing_session_local_opencode_data`、`migrates_all_legacy_profile_data_before_cleanup`、`skips_cleanup_when_migration_fails`、`skips_cleanup_when_shared_target_is_non_sqlite`、`skips_cleanup_when_legacy_source_is_non_sqlite_and_shared_target_is_valid`) | fixture 把旧 session 写到 `real-home/.config/mms/opencode-gateway/s/123`;33fd11fc 之后 `mms_opencode_env.opencode_gateway_env` 的 `gateway_base` 改为 `.config/mms-next`,迁移扫描(`_migrate_opencode_data_to_shared_state`,扫 `sessions_dir` 兄弟目录)扫不到旧 fixture → 不迁移/不报 failed → `fake_cleanup` 里 `shared_db` 不存在(FileNotFoundError)或"不该跑 cleanup"的 throw 被触发(AssertionError) |
| `test_capability_request_shaping.py::test_profile_budget_patch_maps_reasoning_effort` | fixture 写 `tmp_path/mms/provider-profiles.json`(退役根名);`resolve_mms_config_dir` 现在读 `tmp_path/mms-next` → profile 找不到,落回内置 `gemini` profile → `assert 'gemini' == 'gemini-test'` |
| `test_registry_runtime_resolver.py` 2 个(`..._use_legacy_only_when_latest_manifest_missing`、`..._cache_is_scoped_by_config_root`) | 同样写 `<xdg>/mms/provider-profiles.json`,代码读 `<xdg>/mms-next` → `profile_context_window` 返回 None(`assert None == 111000`) |
| `test_mms_state_io.py::test_xdg_config_home_is_not_explicit_preview_root` | 断言 `mode == "stable"` 且 root 为 `xdg/mms`;现在 mode 恒 preview、root 为 `xdg/mms-next` |
| `test_registry_cli.py::test_mms_config_save_plan_blocks_stable_root_without_writing` | 子进程干净 env 跑 `mms config save-plan`,断言 stable 根被 block;现在 mode 恒 preview → `assert 'preview' == 'stable'`。"stable 根"这个概念本身已不存在 |

**建议动作**: fixture 路径统一改 `mms-next`;语义断言(mode/root name)按单一 preview 根重写。10 个一起改是安全的(都是纯测试侧)。

## R4 — main()/启动流程的 preview 化(2 个,C)

- `test_legacy_surface_cleanup.py::test_mms_default_path_still_uses_tui_launcher_handler`: 测试 monkeypatch `mms_core.load_config` 期望默认路径走 TUI handler;但 `main()` 现在走 `_load_config_or_preview_bundle()`(mms_core.py:17283),preview 根下不再调用 `load_config`,空 bundle → `_bootstrap_preview_root_config` 返回 None → `_exit_preview_legacy_config_disabled(["launch"])` → `SystemExit: 2`。**注意它在我本机单独跑会"假通过"**: 不 scrub env 时 `_load_preview_runtime_config_from_latest_bundle()` 读到真实 `~/.config/mms-next` 的 bundle,cfg 非 None → TUI 分支命中。这本身就是这个测试不可靠的旁证。
- `test_model_routes_export.py::test_refresh_routes_export_for_hive_supports_startup_safe_probe`: 3aae0748 起 `_refresh_routes_export_for_hive` 在 `startup_safe` 且 preview 根时直接 return True 不导出(`_usage_routes_export_should_run()` 恒 False)→ `calls == []`。同文件 1112 行的新测试 `test_..._skips_startup_safe_probe_for_preview` 已经覆盖了新行为,旧测试是冗余的过期断言。

**建议动作**: 前者按 bundle bootstrap 流程重写(monkeypatch `_load_config_or_preview_bundle` 而不是 `load_config`);后者可直接删或改成断言 preview 下不导出。

## R5 — resolver 缓存 vs 损坏注入(1 个,C)

`test_registry_runtime_resolver.py::test_capability_resolver_uses_verified_latest_approved_by_default`: 先写合法 bundle、resolve 一次,再把 `generated/model-capabilities.approved.json` 改坏,期望 `CapabilityBundleError` → 实际 DID NOT RAISE。原因: cf914bec 加的 `_load_default_approved_facts_cached` 是 `lru_cache`,key 是 manifest 文件的 (path, mtime_ns, size);测试只改 payload 文件,manifest 签名不变 → 缓存命中 → 不重新校验。测试写于缓存引入之前(2dc1e992)。

**建议动作**: 测试篡改后调 `clear_capability_resolver_caches()`(函数现成,docstring 写明"intended for tests")。若想更严,可让篡改同时 touch manifest;但那是测试写法问题,不是产品 bug——真实 bundle 发布是原子写,manifest 会一起更新。

## R6 — reference 快照目录长大了(2 个,D;其中牵出 1 个 B 类候选)

测试写的时候 `docs/reference/model-capability-calibration/` 只有 `2026-05-21` 一个 JSON;现在有 6 个(新增 2026-09-02 ×3、2026-09-06、2026-09-10,均无 openrouter refs,已逐个核实)。

- `test_refresh_sources_imports_reference_snapshot_to_db`: 只 import `2026-05-21` 一个文件,然后断言 `registry_status()["source_freshness"]["due_count"] == 0`。但 `registry_status` 的 freshness 对默认目录**全部** 6 个 JSON 检查,其余 5 个 never_checked → `due_count == 5`。前提失效型(D)。
- `test_scheduled_refresh_from_file_imports_openrouter_and_candidates`: `scheduled_refresh` 会把所有 due 的默认快照都 import,`diff_openrouter_catalog` 的 baseline 是**最新一个** calibration 快照(`_latest_source_payload`)。现在最新的是 `2026-09-10-deepseek-v41-glm-qwen-tiers.json`,它 **0 条 openrouter refs** → diff 恒空 → `stored_count == 0`,断言 `>= 1` 失败。

**B 类候选(待裁决)**: 第二条暴露的不只是测试问题——自 2026-09-02 起,生产上 scheduled refresh 的 openrouter drift 检测实际已经哑火(baseline 永远是没有 openrouter refs 的最新快照)。是"diff 应合并所有 calibration 快照的 refs"(改代码,B)还是"每快照独立 diff"(改测试,C),需要人定。我倾向 B,但按 packet 要求这里不动代码。

## R7 — 替身签名漂移(2 个,C)

`test_mimo_1m_context.py` 两个测试把 `mms_launchers._claude_route_status_paths` monkeypatch 成零参 lambda;代码在 per-PID 会话隔离改造后(mms_launchers.py:10413)以 `gateway_home=` 关键字调用 → `TypeError: unexpected keyword argument 'gateway_home'`。

**建议动作**: 替身改 `lambda *args, **kwargs`。两分钟的事。

## R8 — 有意退役的 surface(2 个,C)

- `test_mmc_isolation.py::test_build_session_settings_only_uses_repo_allowlisted_hooks`: 断言 hooks == `{"PreToolUse", "PostCompact"}`;f239cbba "retire automatic continuation and indexing hooks" 后代码只产 `PreToolUse`。
- `test_agy_launcher.py::test_agy_session_assets_overlay_common_skills_mcp_and_hooks`: 断言 web-access 的 SKILL.md 被 link;9ab22bec 起 `_overlay_web_access_session_entries` 是有意 no-op(注释: "web-access is a Weber backend, not a user-facing session skill")。

**建议动作**: 更新断言到新契约(PostCompact 移除;web-access 不再出现在 session skills)。

## R9 — 环境变量隔离缺口(3 个,D)——packet 63 vs 我 65 的全部差额

| 测试 | 触发变量 | 验证 |
|---|---|---|
| `test_legacy_surface_cleanup.py::test_mms_chat_discuss_direct_commands_are_disabled_by_default` | `MMS_COMMAND_NAME`(我的 shell = `mmf`)→ `current_command()` 优先读它,输出变成 `` `mmf chat` `` | `env -u MMS_COMMAND_NAME` 后单独跑**通过**(已实测) |
| `test_pi_launcher.py::test_launch_pi_rewrites_deprecated_antigravity_gemini_alias_to_live_replacement` | `MMS_PI_SKILLS_OVERLAY`(gateway 会话注入)→ 启动 cmd 多 `--no-skills --skill <path>` | `env -u` 后**通过**(已实测) |
| `test_committee_timing.py::test_timing_log_path_defaults_to_mms_next_under_real_home` | conftest 全局注入的 `XDG_CONFIG_HOME`(296adaf4)→ `timing_log_path()` 命中 case 1 而非测试预期的 case 3 | 直接调 `timing_log_path(env)` 传无 XDG 的 env map 返回预期路径(已实测);测试只需补 `delenv("XDG_CONFIG_HOME")` |

**建议动作**: 三个都是测试内补 `monkeypatch.delenv`。另外建议把这三个变量加进 `scripts/ci_pytest_regression.py::_clean_env()`(它现在只清 8 个 MMS 变量,不含这三个)——否则 gate 的 base run 在开发者本机同样脏。这属于"建议",不在本阶段改动范围。

## R10 — 测试间污染: 全局 UI 语言被翻成英文(1 个,D)

`test_managed_skill_imports.py::test_build_confirm_preview_catalog_includes_managed_dynamic_skills`: 单独跑、整文件跑都**通过**;全量跑必挂,断言 `(label == "路径")` 失败因为 label 变成了 `"Path"`。

**污染源定位(实测 bisect)**: 任一调用 `mms_core.main()` 的测试(本机 locale 为 `en_US`)都会在 main 里命中 `set_language(_resolve_ui_language(None, ...))` → locale 回退到 `en` → `mms_i18n._CURRENT_LANGUAGE` 模块级全局被永久改成英文,monkeypatch 不会还原它。最小复现: `pytest tests/test_legacy_surface_cleanup.py::test_mmf_missing_preview_config_does_not_run_legacy_setup tests/test_managed_skill_imports.py::test_build_confirm_preview_catalog_includes_managed_dynamic_skills` → 后者必挂。按字母序 test_legacy_surface_cleanup 在 test_managed_skill_imports 之前,全量跑稳定触发。

**建议动作**(packet 说这类最值得修): 双向修——(a) 调用 main() 的测试在 teardown 里 `mms_i18n.set_language("zh")` 或 conftest 加 autouse fixture 每个测试后复位语言;(b) 断言中文 label 的测试开头显式 `mms_i18n.set_language("zh")`(test_legacy_surface_cleanup.py 里已有 7 处这种先例)。推荐 (a) 的 conftest autouse 方案,一次修掉一类。

---

## 波动性 / 和 packet 的 63 对账

- 两次全量跑(相同命令、相同 commit)失败集合 **逐条一致**,无 flake。
- packet 在 `f663db83` 数到 63;我在 `a0f77398` 数到 65。两个 commit 之间(`e6f3a575` release + `a0f77398` changelog)不改任何被测代码,差异全部来自 R9: packet 作者的 shell 里没有 `MMS_COMMAND_NAME` / `MMS_PI_SKILLS_OVERLAY`,我的有(gateway 会话注入)。去掉这两条环境敏感项,63 = 65 - 2,逐条吻合(packet 分布里 `test_legacy_surface_cleanup` 1 条即 default_path,无 `test_pi_launcher`)。
- 也就是说: **CI/干净机器上是 63,带 gateway 环境的 dev shell 里是 65**,两边各自稳定。R9 修掉后任何环境都是同一个数。

## 修完后基线预估

全部按上表修(纯测试侧,不动产品代码;R6 的 B 类候选若裁为改代码则另算):

- failed: 65 → **0**(A 类为 0,没有需要转 skipif 的;36 个 skipped 保持不变)
- passed: 2425 → **2490**
- CI 回归门从此对全量测试生效,digger 的 P2 基线噪音消失

## ci_pytest_regression.py 核对(packet 要求)

packet 的描述**正确**: `candidates = head_failures - base_failures`,base 红 + head 红 → 不进 candidates → 不参与门禁;另有 `FLAKE_RERUNS = 2` 只对 candidates 重跑,对恒红测试无影响;`fixed = base - head` 只打印不拦截。补充一个 packet 没提的点: `_clean_env()` 清了 8 个变量但**不含** `MMS_COMMAND_NAME`、`MMS_PI_SKILLS_OVERLAY`、`LANG`/`LC_ALL`——即 R9/R10 的污染在 gate 的 base/head 双跑里同样存在(只是两边对称,不产生假 regression)。R9 的三个测试在 CI runner(无这些变量)上其实是绿的,这解释了为什么 CI 没有整体爆炸。

## 本阶段边界执行声明

- 一行产品/测试代码都没改;工作区只有本报告、`.t8c/` 诊断日志和 `.ai/regression-reports/` 记录。
- 未碰 8767/60824/8765/8766 端口,未 `pkill`,未写真实 `~/.config/mms*`(两次全量跑均按 packet 做 env 隔离,真实根只发生过只读 `ls`)。
- 没有删测试、没有标 xfail。
