# T9a — 仓库首页要滚 121 行才看得到 README

**base**:`main`。合了之后按常规回流 `dev`。

**机主已经批了破坏性做法**（2026-09-18）：旧安装不做兼容，但必须报错并引导更新，见第三节第 5 条。

**这不是美观问题。** 机主的原话：「有大量的脚本在 repo 的根，导致需要滚动很久才能滚动到底部看内容」。GitHub 把文件列表排在 README 之前，而我们的根目录有 **121 个条目**，其中 **80 个是 `mms_*.py` / `mmc_*.py`**。任何第一次点进这个仓库的人，先看到的是 80 行看不懂的文件名。

GitHub 没有折叠根列表的机制，没有 `.gitattributes` 开关，没有任何配置能让 README 上移。**唯一的解法是根目录条目变少。**

---

## 一、现状的准确数字

```
git ls-tree origin/main | awk '{print $2}' | sort | uniq -c
  105 blob
   16 tree
```

105 个文件 + 16 个目录 = 121 行。其中：

| 类别 | 数量 |
|---|---|
| `mms_*.py` / `mmc_*.py` 顶层模块 | 80 |
| 入口脚本（`mms` `mmf` `mmm` `mms-web` `mmslogs` `install.sh` `*.command` `statusline-command.sh`） | 9 |
| 文档 / 配置 / 元数据 | 16 |
| 目录 | 16 |

把 80 个模块收进一个目录，根目录就变成 **约 42 行**。这是唯一一个量级上有意义的动作，其它都是零头。

---

## 二、为什么这件事比看起来简单

这 80 个模块全是**平铺的顶层模块**，彼此之间用 `import mms_core` 这种形式互相引用。它们能被 import，靠的是入口脚本把**仓库根**插进 `sys.path`：

```python
# mms:7-8
ROOT = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, ROOT)
```

所以：**把这 80 个文件整体移进一个目录，然后把那个目录（而不是仓库根）插进 `sys.path`，所有 `import mms_xxx` 语句一行都不用改。**

这是整个包的核心判断。不要把它做成「引入 package 并把所有 import 改成 `from mms.core import ...`」——那是几千处改动、无数隐式循环依赖、以及一次巨大的 review 负担，换来的收益和上面这个做法完全一样。

**目录名建议 `lib/`。** 不要用 `mms/`：根目录已经有一个叫 `mms` 的可执行脚本，同名会在大小写不敏感的文件系统上直接炸。`src/` 也可以，但 `lib/` 更准确（这些不是待构建的源码，是运行时直接加载的模块）。名字你定，在交付里说明理由即可。

---

## 三、要改的地方（这是全部，不要多改）

### 1. 文件移动

`git mv` 那 80 个 `mms_*.py` / `mmc_*.py` 到 `lib/`。**只移动，一个字节都不改内容。**

> `mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py` 是受保护文件。**本包对它们的边界是：只改路径，不改任何一行内容。** 交付里要能用 `git log --follow` 或 `git diff -M` 证明这一点。

`mms_version.py` 也在其中——注意第 5 条。

### 2. sys.path 注入点

入口脚本改成插入 `lib/`：`mms`、`mmf`、`mmm`、`mms-web`、`mmslogs`、`MMS Pilot.command`、`MMS Installer.command`、`statusline-command.sh`、`hooks/` 下任何计算根目录的脚本。

`grep -rn "sys\.path\.\(insert\|append\)"` 在跟踪文件里有 **39 处**（排除 `node_modules` / `vendor`）：4 处在 `mms_web/`、9 处在 `scripts/`、24 处在 `tests/`、1 处在 `apps/runtime-api/scripts/`、1 处在 `mms_review_dispatch_execute.py`。它们大多是 `ROOT = Path(__file__).resolve().parents[1]` 这种形状，**逐个核对**移动后还指向能 import 的位置。

`mms_web/service.py:582` 的 `env.setdefault("PYTHONPATH", str(source_root()))` 和 `source_root()` 本身必须一起看。`tests/` 里另有约 20 处 `PYTHONPATH=str(ROOT)`（集中在 `test_registry_cli.py`）。

### 3. 安装器

`install.sh` 里至少这些点：

- 三处把 `mms_core.py` 当作「这是不是一份 MMS 源码」的哨兵：`:122`、`:511`、`:2693`。
- `:2713-2716` 显式 `cp` 的四个文件。
- `:2728-2729` 的 `for f in "$SOURCE_DIR"/mms_*.py` 循环。
- `:2162` 读 `mms_version.py` 的路径。
- `:1426` 调用 `mms_hook_retirement.py` 的路径。

`mms_web/update_install.py` 的 `FILES` / `GLOBS`（`"mms_*.py"`）/ `DIRECTORIES` —— 注释明说它 "Mirrors the copy list in install.sh"，两边必须同时改，形状保持一致。

### 4. 其它路径引用

`.github/workflows/digger.yml`、`package.json`、`.codexignore`、`docs/` 里出现 `mms_hook_retirement.py` 这类相对链接的地方（`docs/BUNDLED_PACKS.md` 里有一个）。

### 5. 旧安装不做兼容,但必须**报错并引导更新**(机主 2026-09-18 决定)

机主的原话:「我就是希望所有旧的 mms 配置的用户都做成让他们更新,所以他们不能用根本无所谓(其实也没几个用户)。如果你觉得需要,就做一个他们执行报错后的兼容,让他们执行后引导更新吧。」

**所以这个包不需要向后兼容旧布局。** 不要写双路径 sys.path、不要写 fallback import、不要试图让旧 `~/.mms` 继续工作。

但有一件事仍然是必须的,而且理由变了:

> **旧平铺副本必须被删除,不是因为怕用户装不上,而是因为它不报错。**
>
> 现有用户的 `~/.mms/` 里躺着 80 个平铺的 `mms_*.py`。如果升级后新代码装进 `~/.mms/lib/` 而旧平铺文件还在、并且安装根仍在 `sys.path` 上,Python 会**先找到旧文件**。结果是用户静默跑上一个版本的代码,而版本号显示新版本。**静默跑旧代码比干脆报错糟得多**,也正好违背机主要的「报错后引导更新」。

所以两条都要做:

**(a) 清掉旧副本。** 安装器和 Pilot 内升级在写入新布局之后,删除 `~/.mms` 根下那批旧平铺模块。**按精确文件名清单删**,不要用 `rm mms_*.py` 通配——那会连带删掉用户自己放在那里的东西。同时 `sys.path` 只插 `lib/`,**不要**同时保留安装根;两个都在,shadow 就依然存在。

**(b) 布局守卫:报错要是人话,不是 traceback。** 每个入口脚本在 import 任何 MMS 模块**之前**,先确认模块目录存在且可用。不成立时不要让 `ModuleNotFoundError` 甩出来,而是打印一段明确的引导然后以非 0 退出:

```
这份 MMS 安装是旧布局(模块在安装根,当前入口需要 lib/)。
旧布局不再被支持,请重新执行安装命令更新:

  curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash

如果 Pilot 正在运行,先执行 mms web stop 再装。
```

英文版同形状(安装器本身是双语的,跟它一致)。要覆盖的入口:`mms`、`mmf`、`mmm`、`mms-web`、`mmslogs`、`MMS Pilot.command`、`MMS Installer.command`。

**`statusline-command.sh` 是例外**:它的输出会被渲染进状态栏,不能打印多行。那里降级成一行短提示(例如 `MMS: 需要重新安装`),不要把上面那段塞进状态栏。

**(c) Pilot 更新中心也要说对话。** 如果它检测到混合布局,提示必须是「需要重新运行安装命令」,**不能**表现成普通的「有新版本可用」——后者会让用户点了更新却还是旧布局。如果这一条的实现成本明显超出本包范围,可以只在交付里写明并单独立包,但**要明确说**,不要静默略过。

### 6. 不要做的

- **不要**改任何 import 语句。
- **不要**顺手拆分、合并、重命名任何模块。这个包只搬家。
- **不要**碰 `mms_web/`、`apps/`、`tests/` 的目录结构。
- **不要**在这个包里同时做别的根目录清理（删文档、挪脚本）。那些已经在 docs 整理里做完了。
- **不要**新建 `__init__.py` 把 `lib/` 变成 package。它就是一个 sys.path 目录，加了 `__init__.py` 反而会让 `import mms_core` 的语义变得可疑。

---

## 四、测试

这个包的风险不在「能不能 import」——那个一跑就知道。风险在**安装后的布局**和**旧副本 shadow**。

1. **新布局能启动**：`python3 ./mms --help`、`python3 ./mms doctor`、`python3 -m mms_web --help` 全部正常。
2. **安装器产出正确布局**：`bash install.sh --dry-run` 的计划里包含 `lib/`，不包含根级 `mms_*.py`。
3. **覆盖安装会清掉旧平铺副本**：预置一个带 80 个平铺模块的假 `~/.mms`，跑安装，断言它们不在了、`lib/` 在了，并且断言删除是按精确清单做的（预置一个用户自己的 `mms_myhack.py`，断言它**还在**）。
4. **不会 shadow**：造一个「安装根有旧平铺 `mms_version.py`、`lib/` 里有新的」的目录，断言实际 import 到的是 `lib/` 里那个。
5. **旧布局给人话,不是 traceback**：把模块目录搬走或改名，执行入口脚本，断言 stdout/stderr 里出现引导文案和那条 `curl` 命令、**不出现** `Traceback` 或 `ModuleNotFoundError`、退出码非 0。每个入口各一条。
6. **statusline 不刷屏**：同样的坏布局下执行 `statusline-command.sh`，断言输出只有一行。
7. **Pilot 内升级同样正确**：`tests/test_update_install.py` 里加一条，断言 `FILES`/`GLOBS`/`DIRECTORIES` 装出来的布局和 `install.sh` 一致，且旧平铺副本被清理。

**mutation（每条自己跑，记录红/绿）**：

- 把入口脚本的 `sys.path` 改回插入仓库根 → 第 1 条必须红
- 把安装器里清理旧平铺副本的那段删掉 → 第 3 条必须红
- 把清理改成 `rm mms_*.py` 通配 → 第 3 条里「用户自己的文件还在」那个断言必须红
- 在 `sys.path` 里同时保留 `lib/` 和安装根 → 第 4 条必须红
- 把布局守卫删掉（让 import 自己抛 `ModuleNotFoundError`）→ 第 5 条必须红
- 把守卫里的 `curl` 命令删掉、只留一句「布局不对」→ 第 5 条必须红
- 让 `statusline-command.sh` 直接复用多行守卫 → 第 6 条必须红
- 把 `update_install.py` 的 `GLOBS` 留成 `"mms_*.py"`（不跟着改）→ 第 7 条必须红

倒数第五条和第四条特别重要：它们分别守着「报错要是人话」和「不能静默跑旧代码」，是机主对这个包唯一提出的两点要求。

---

## 五、门禁

- `python3 scripts/ci_pytest_regression.py --base origin/main`。**这个包会动 39 处 sys.path，期望是 0 新增失败。** 写 base/head 绝对数。
- `python3 scripts/regression_fresh_user_gate.py`（完整，不加 `--quick`）。这个包动的就是安装 / 路径 / config root 路径，**gate 必跑**。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`；它对并发敏感，串行跑一次。
- `bash install.sh --check` 和 `bash install.sh --dry-run`（`--dry-run` 必须不写任何文件）。
- Windows CI 矩阵（`windows-2022` / `windows-2025`）必须绿——Windows 的路径处理和大小写敏感性是这个包的天然雷区。
- 不碰前端，不用重建 bundle，在交付里说明。

---

## 六、边界

- 只做搬家和路径修正。受保护文件的边界是「只改位置，不改内容」。
- **绝不**碰端口 8767 / 60824 / 8765 / 8766；起验证实例用 61000-62000 的随机端口，**只 kill 自己启动的 PID**，绝不 `pkill`，绝不按端口 grep 后批量 kill。
- **绝不**写机主真实的 `~/.mms`、`~/.config/mms*`、`~/.local/share/mms-web`。第三节第 5 条那些测试全部用临时目录，跑前确认隔离生效。
- 别人的工作树里有未提交改动，在自己的 worktree 里干活，不要 stage / stash / reset 任何不属于本包的文件。

---

## 七、交付

- 提 PR，base 填 `main`，**不要** merge。
- 交付里必须写清：
  1. 选了哪个目录名，为什么。
  2. `git diff -M --stat` 证明 80 个文件是纯 rename（受保护文件尤其要能看出来）。
  3. 每条 mutation 的红/绿。
  4. 门禁实测绝对数，含 Windows CI。
  5. **旧平铺副本的清理策略具体是怎么实现的，以及你怎么验证它真的生效。** 这一条写不清楚就不要提 PR。
  6. 旧布局下每个入口的**实际输出原文**（贴出来），证明里面没有 traceback、有那条 `curl` 命令。
  7. 第三节 5(c)（Pilot 更新中心的提示）是做了还是单独立包。**不允许不提。**
  8. 合并后 `git ls-tree origin/<branch> | wc -l` 的实际数字（预期约 42）。

**这个包合了之后要尽快发版**，因为老用户的 `~/.mms` 里会同时存在两套布局，越晚发、跨版本的组合越多。
