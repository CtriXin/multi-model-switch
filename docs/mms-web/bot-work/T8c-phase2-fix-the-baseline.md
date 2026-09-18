# T8c 第二阶段 — 把基线修到 0 failed

**base**:`main`。第一阶段的分类报告在 `docs/mms-web/bot-work/T8c-pytest-baseline-report.md`(已合进 `main`),**先读它** —— 那份报告的每一组都给了 traceback 级的证据链和建议动作,这个包只补裁决和边界。

**先说结论**:第一阶段做得很好。65 个失败 → 10 个根因、两次全量跑逐条一致无 flake、63 vs 65 的差额对账到具体环境变量、`ci_pytest_regression.py` 的行为核对无误还顺手挖出它 `_clean_env()` 的缺口,而且一行代码没改。这一轮按它的建议动作做。

---

## 我的三个裁决

### 裁决一 · R6 的 B 类候选:是 B,要改代码

报告说得对,而且这条比它自己标的份量更重:**自 2026-09-02 起,生产上 scheduled refresh 的 openrouter drift 检测实际已经哑火。** `diff_openrouter_catalog` 的 baseline 取 `_latest_source_payload`(最新一个 calibration 快照),而 2026-09-02 之后新增的 5 个快照**一条 openrouter refs 都没有**,所以 diff 恒空、`stored_count == 0`。

报告问"是改代码(diff 合并所有 calibration 快照的 refs)还是改测试(每快照独立 diff)"。**改代码。** 理由:drift 检测的目的是发现 openrouter 目录相对**我们已知的全部 refs**有没有变化,而不是相对"最近一次恰好录了 refs 的那个快照"。每快照独立 diff 在语义上讲不通 —— 快照之间本来就互不相同,逐个 diff 只会产生噪音。

所以:**baseline 改成所有 calibration 快照 refs 的并集**(按 model 去重,同一 model 出现在多个快照时取最新那个快照的值)。改完之后那条测试应该**因为真实原因**变绿,而不是因为断言被放宽。

这是这一轮里唯一动产品代码的地方。改动要小、要有自己的测试,并且在交付里单独说明。

### 裁决二 · R1 的产品边界:先回答,再决定怎么修

报告在 R1 里留了一个问题:fail-closed 对"全新 preview 根、还没发过 bundle"的真实安装也生效;真机上 `~/.config/mms-next/generated/` 有 bundle 所以正常不触发,但"首次启动尚未 publish bundle 时 opencode 启动链路是否会撞到"没验证。

**这个必须先回答,因为答案决定 R1 那 35 个是 C 类还是 B 类。**

怎么回答:
- `scripts/regression_fresh_user_gate.py` 是模拟全新安装的,看它**有没有覆盖 opencode 启动路径**。如果覆盖了而且是绿的,说明安装流程会 publish bundle,R1 就是纯测试问题(C),按报告的建议补 fixture 即可。
- 如果 gate 没覆盖 opencode 启动,**补一条场景**:临时 HOME、全新 `~/.config/mms-next`、不预置任何 bundle,然后走一次 opencode 启动。看它是 fail-closed 报错还是正常工作。
- 如果真的会撞 —— 那就是影响新用户的产品 bug,**停下来告诉我**,不要自己改产品代码绕过 fail-closed。fail-closed 本身是 `mms_capability_resolver` 模块 docstring 写明的设计意图("Explicitly selected preview roots must not silently continue"),不能因为测试不方便就放宽它。

### 裁决三 · R9 的 gate 脚本:修

报告把"把三个变量加进 `scripts/ci_pytest_regression.py::_clean_env()`"列为建议、不在阶段范围。**做掉。** 它现在只清 8 个 MMS 变量,不含 `MMS_COMMAND_NAME`、`MMS_PI_SKILLS_OVERLAY`,也不含 `LANG` / `LC_ALL`(R10 的污染源)。

后果是实在的:CI runner 上没有这些变量所以看不出问题,但**开发者在本机跑 `ci_pytest_regression.py` 时 base 和 head 双跑都是脏的**。虽然两边对称、不产生假 regression,但它让"本地跑一次确认"这件事失去意义 —— 而每个包的交付要求里都写着让执行方本地跑这个。

---

## 要做的事,按批

### 批 A · 纯测试侧,可以一起做(R2 R3 R4 R5 R7 R8 R9 R10)

报告里每组的"建议动作"直接照做。合计 24 个测试 + gate 脚本。

几个要点:

- **R10 用 conftest autouse 方案。** 报告推荐的 (a):在 conftest 加一个 autouse fixture,每个测试后把 `mms_i18n._CURRENT_LANGUAGE` 复位。这一次修掉一类污染,比逐个测试开头 `set_language("zh")` 好。注意别把复位写成"设成 zh" —— 应该是**保存进入时的值、退出时还原**,否则会把另一类假设反过来。
- **R4 的第二条**(`test_refresh_routes_export_for_hive_supports_startup_safe_probe`)报告说"可直接删或改成断言 preview 下不导出",而且同文件已有新测试覆盖新行为。**删它**,并在交付里说明哪条新测试接管了覆盖。
- **R9 的三个测试**各自 `monkeypatch.delenv`,同时改 gate 脚本(裁决三)。改完之后,报告里那句"CI 上是 63、带 gateway 环境的 dev shell 里是 65"应该变成**任何环境都是同一个数**。

### 批 B · R1 那 35 个(等裁决二的答案)

先回答产品问题,再动手。如果确认是纯测试问题,按报告建议给这批一个共享 fixture(在临时 config root 里写最小 latest-approved bundle,现成写法在 `tests/test_registry_runtime_resolver.py::_write_bundle`),或者 monkeypatch `_load_default_approved_facts_shared`(先例在 `test_mimo_1m_context.py:163`)。

**注意 `test_config_web.py` 那两条是"哑火版"** —— `_model_capability_defaults` 用 `except Exception: pass` 吞掉异常,capability 落回保守默认。修它们的时候顺便看一眼:**那个裸 `except Exception: pass` 本身合理吗?** 它会把任何异常都变成"保守默认",包括不该被吞的。如果你认为它该收窄,单独说明,不要在这个包里顺手改。

### 批 C · R6(裁决一,动产品代码)

改 `diff_openrouter_catalog` 的 baseline 取法,加自己的测试。

---

## 防偷懒:这一轮的硬要求

修"过期断言"最容易的偷懒方式是**把断言删掉、改成永真、或者放宽到测不出东西**。所以:

**每修好一组,把那组测试对应的产品行为改坏,测试必须红。**

举例:
- R2 修完 fixture 之后,把 `mms_pi_support.py` 那条"必须显式声明 protocols"的检查删掉 → `test_pi_committee.py` 应该有测试变红(或者至少行为可辨)
- R7 替身改成 `**kwargs` 之后,把 `_claude_route_status_paths` 的 `gateway_home` 参数去掉 → 测试要能看出来
- R8 更新断言之后,把 `PostCompact` hook 加回去 → 那条断言必须红
- R10 的 conftest fixture 加上之后,把它删掉 → `test_managed_skill_imports` 在全量跑里必须重新变红

**每一组都要有这样一条,写进交付。** 一组都不能少。这是这一轮唯一能证明"修好的测试还在测东西"的办法。

另外:
- **不许删测试**(R4 第二条是唯一例外,而且要说明谁接管了覆盖)
- **不许标 `xfail`**
- **不许为了让数字好看而放宽断言**

---

## 验证

- **最终目标**:`env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME python3 -m pytest tests/ -q -p no:randomly` 在 `main` 上 **0 failed**。报告预估是 0 failed / 2490 passed / 36 skipped(如果 R6 裁为改代码,passed 可能多 1-2)。
- **跑两次**,确认失败集合(空)稳定,而且 `-p no:randomly` 去掉之后也是 0 —— 随机顺序能暴露剩余的测试间污染。
- `python3 scripts/ci_pytest_regression.py --base origin/main`(改完 `_clean_env()` 之后跑)。
- `python3 scripts/regression_fresh_user_gate.py`(完整,不加 `--quick`)—— 裁决二需要它,而且你可能要给它补一条场景。串行跑一次;`test_install_script_paths.py::test_installer_does_not_reuse_another_homes_web_instance` 对并发敏感,红了单独复跑确认并如实写明。

---

## 边界

- **批 C 是唯一允许动产品代码的地方。** 其余全部是测试侧。
- **不要**动 `scripts/ci_pytest_regression.py` 的判定逻辑(`candidates = head_failures - base_failures` 那套是对的),只改 `_clean_env()` 的变量清单。
- **不要**放宽 `mms_capability_resolver` 的 fail-closed 行为。它是有意设计的。
- **不要**动保护文件:`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`。R7 涉及 `mms_launchers.py` 的**替身签名**,改的是测试里的 lambda,不是那个文件本身 —— 别搞混。
- **绝不**碰端口 8767 / 60824 / 8765 / 8766。这个任务基本不需要起服务;真要起,用 61500-61599(其他端口段有别的验收方在用),**只 kill 自己启动的 PID**,绝不按端口或进程名批量 grep 后 kill,绝不用 `pkill`。
- **绝不**写真实 `~/.config/mms*`。
- 在自己的隔离 worktree 里干活,用完 `git worktree remove`。不要碰 `.worktrees/` 下任何已有目录。

## 交付

- 提 PR,base 填 `main`,**不要** merge。
- 交付里写清:每组改了什么、防偷懒那条 mutation 的结果(改坏产品行为 → 哪条测试红)、最终 pytest 实测数、裁决二的答案(fresh-user gate 覆盖了吗?全新安装会不会撞 fail-closed?)。
- 如果批 B 的产品问题答案是"会撞",**停在那里报告**,批 A 和批 C 照常交付。
