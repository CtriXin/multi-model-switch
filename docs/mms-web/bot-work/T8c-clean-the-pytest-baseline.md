# T8c — 把 pytest 基线洗干净

**base**:`main`。这是一个**诊断 + 分类**任务,不是一上来就改代码的任务。第一阶段只产出一份表和一个结论,改不改、怎么改由那份表决定。

**可以立刻开工**,不依赖任何在飞的 PR。它是纯只读的调查,不碰任何别人正在改的文件。

---

## 为什么要做

`main` 上有 63 个测试在任何分支上都是红的。我刚在 `f663db83`(当前 `main` tip)上跑了一次完整的:

```
63 failed, 2427 passed, 36 skipped, 2 xfailed, 4 subtests passed in 557.60s
```

后果有三个,都是真的:

1. **CI 的回归门被噪音淹没。** `scripts/ci_pytest_regression.py` 的做法是"在 base 跑一遍、在 head 跑一遍,只对 base 通过而 head 失败的测试报错"。这个设计本身是对的,但它意味着**这 63 个测试永远不参与门禁** —— 它们在 base 红、在 head 也红,所以任何在它们覆盖范围内的新回归都不会被拦住。
2. **digger 每次 review 都要报一条 P2。** 原文:`[P2] Existing baseline validation failures remain. No new head failure was introduced, but the base still has failing validation.` 每个 PR 都带着这句,久了就没人看了。
3. **每次人工验收都要先扣掉这堆噪音才能判断有没有真回归。** 这一轮里每个验收方都花了时间在"这个失败是新的还是既存的"上。

---

## 失败的分布(我实测的)

```
  37  tests/test_opencode_launcher.py
   7  tests/test_pi_committee.py
   3  tests/test_registry_runtime_resolver.py
   3  tests/test_registry_cli.py
   2  tests/test_mimo_1m_context.py
   2  tests/test_config_web.py
   1  tests/test_model_routes_export.py
   1  tests/test_model_name_exports.py
   1  tests/test_mms_state_io.py
   1  tests/test_mmc_isolation.py
   1  tests/test_managed_skill_imports.py
   1  tests/test_legacy_surface_cleanup.py
   1  tests/test_committee_timing.py
   1  tests/test_capability_request_shaping.py
   1  tests/test_agy_launcher.py
```

**关键观察:一个文件占了 59%。** `test_opencode_launcher.py` 的 37 个失败几乎不可能是 37 个独立问题 —— 大概率是一个共同根因(某个 fixture、某个前置条件、某个被改过但测试没跟上的接口)。同理 `test_pi_committee.py` 的 7 个。

所以这 63 个很可能只有 **5 到 8 个根因**。这是这个任务可做的原因。

复现命令(我用的就是这个):

```bash
python3 -m pytest tests/ -q -p no:randomly
```

`-p no:randomly` 是为了让失败集合稳定可比。跑一次约 9 分钟。

---

## 第一阶段:分类(必须先做完这个)

对**每一个**失败,判断它属于哪一类,产出一张表。

分类只有这四种:

| 类 | 含义 | 怎么处理 |
|---|---|---|
| **A · 环境依赖** | 测试需要本机装了某个东西(opencode / pi / 某个 CLI / 某个网络端点),在没装的机器上必然红 | 应该 `skipif` 而不是 fail —— 让"没装"表现为 skip |
| **B · 真 bug** | 测试是对的,被测代码确实坏了 | 要修代码。**这一类最重要,单独列出来** |
| **C · 过期断言** | 行为被有意改过,测试没跟上 | 要改测试,并说明旧断言为什么不再正确 |
| **D · 测试自己坏了** | 测试写错了、fixture 失效、测试之间互相污染 | 要修测试 |

表的格式:

| 测试 | 类 | 根因(一句话) | 和别的失败共享根因吗 | 建议动作 |
|---|---|---|---|---|

**先按根因归组再填表。** 如果 37 个 opencode 失败是同一个根因,那就是表里一行覆盖 37 个测试,不要写 37 行。

### 这一阶段的硬要求

- **每一条的根因都要有证据**:跑单个测试的实际输出,或者代码里那处不一致的位置。不许写"可能是环境问题"。
- **不许改任何代码。** 这一阶段的产出只有那张表 + 一个结论段。
- **`ci_pytest_regression.py` 要读一遍**,确认我上面对它行为的描述是对的(base 红 + head 红 = 不报错 = 不参与门禁)。如果我说错了,在交付里纠正我。

---

## 第二阶段:按类处理(等我看过表再动)

第一阶段的表交给我,我按类裁决要不要做、做哪些。**不要自己往下做第二阶段。** 原因:B 类(真 bug)可能牵扯到保护文件或启动链路,那需要单独的边界说明;而 A 类(环境依赖)改 `skipif` 看着简单,但"哪些环境算合法缺失"是个约定问题,不是实现问题。

不过你可以在表里给出建议,包括:

- A 类:建议用什么条件 `skipif`(`shutil.which("opencode")`?某个环境变量?),以及改完之后 `main` 的 pytest 会变成多少 passed / 多少 skipped
- B 类:按影响面排序,并标出哪些碰到了保护文件(`mms_core.py` / `mms_launchers.py` / `mms_tui.py` / `mms_bridge.py` / `mms_account_state.py` / `mms_session.py` / `mms_adapter_registry.py` / `mms` / `ccs`)
- C/D 类:哪些能安全地一起改

---

## 边界

- **这一阶段一行代码都不要改。** 包括不要"顺手"修一个看起来很明显的。
- 不要动 `scripts/ci_pytest_regression.py` 的逻辑。它的设计是对的,问题在基线脏,不在它。
- 不要为了让数字好看而把测试删掉或标 `xfail`。`xfail` 是"我们知道它坏且暂时接受",用在这里等于把问题藏起来 —— 除非某一条真的属于这种情况,而且你说明了为什么。
- **绝不**碰端口 8767 / 60824 / 8765 / 8766(机主自己的 Pilot)。这个任务基本不需要起服务,如果某个测试要,用 61000-62000 的随机端口。
- **绝不**用 `pkill`,**绝不**写真实 `~/.config/mms*`。跑测试前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`。
- 在自己的隔离 worktree 里干活,用完移除。不要碰 `.worktrees/` 下别人的现场。

---

## 交付

- 一份 md,放 `docs/mms-web/bot-work/` 下,名字 `T8c-pytest-baseline-report.md`。
- 内容:那张表 + 根因归组 + 每类的建议 + "改完之后基线会变成什么样"的预估。
- 提 PR(docs-only),base 填 `main`。**不要** merge。
- 交付里写明:你跑了几次、失败集合稳定吗(同样的 63 个吗,还是有波动)。**如果有波动,波动的那几条单独标出来** —— 那可能是测试互相污染,属于 D 类里最值得修的。
