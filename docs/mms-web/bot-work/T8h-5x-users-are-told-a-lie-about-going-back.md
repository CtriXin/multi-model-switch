# T8h — 装了 5.x 的用户选回稳定版,界面会告诉他一句假话

**base**:`main`(`updates.py` / `UpdateCenter.tsx` 两条线同源)。修一次回流 `dev`。

**这不是推测。** 机主今天亲身踩了:他在 Pilot 里升到 5.0.6,之后想回 4.x,找不到路。我开了 #316 想修,被作为 superseded 关掉,关闭理由写的是「选择 stable 仅改变检查通道,降回 4.x 需要安装器」。

**那个判断是对的 —— #316 确实修不动这件事。** 但结论不能停在这里,因为界面现在会对用户说谎。

---

## 一、代码事实

`mms_web/updates.py:217-218`:

```python
remote, current = version_tuple(latest.get('tag')), version_tuple(VERSION)
available = bool(remote and current and remote > current)
```

**只有更高的版本才算「有更新」。** 通道切换只换查询哪个 API(`/releases/latest` vs 预览列表),不改这条比较。

于是在一台 5.1.0 的机器上:

1. 用户在「更新通道」里选「4.x 稳定版」
2. 后端查到 stable 最新是 `v4.23.0`
3. `remote(4,23,0) > current(5,1,0)` → **False**
4. `updateAvailable: false`

`apps/mms-web/src/UpdateCenter.tsx:90` 于是渲染:

```
已是最新 4.x 稳定版
```

**这台机器跑的是 5.1.0。** 界面告诉用户他在最新的 4.x 稳定版上。这是一句当面的假话,而且用户没有任何线索能看出不对 —— 弹窗头部的「当前版本 v5.1.0」和这句话之间没有任何冲突提示。

### 还有两处承诺没兑现

- `UpdateCenter.tsx:93`(preview 模式下常驻):「切回 4.x 稳定版即可继续留在稳定线。」
- `docs/mms-web/RELEASE-v4.22.3.md`:「选回稳定版就继续留在稳定线,**随时可逆**。」

两句都在承诺一个不存在的能力。

---

## 二、不要做什么(先说这个)

**不要实现一键自动降级。** 这是本包最重要的边界。

5.x 在 `~/.local/share/mms-web` 下写了 4.x 完全不认识的东西:Bot 工作台的 bots、schedules、bot memory、任务队列。把代码换回 4.23.0 之后这些状态没有任何东西会去读它、迁移它或警告它。一个静默的一键降级会把用户的 Bot 配置变成孤儿数据,**用一个数据问题换另一个数据问题**。

`available = remote > current` 这条比较是对的,**不要动它**。

---

## 三、要做什么

### 1. 那句假话必须先消失(必须)

`UpdateCenter.tsx` 里「已是最新 X」这句,只有在 `latest.tag` 和 `currentVersion` **同属一条线**时才成立。当前版本是 5.x 而所选通道是 stable(或反过来)时,不能说「已是最新」。

具体文案你定,但必须让用户看出「我现在不在这条线上」。**这条是 P0**,其余可以分批。

### 2. 用已有的 `upgradeGuidance` 给出真正的出路(必须)

**不用新建机制。** `mms_web/update_guidance.py` 的 `upgrade_guidance()` 已经会返回 `{required, title, reason, command, steps}`,`UpdateCenter.tsx:97-104` 已经把它渲染成一个带「复制命令」按钮的区块。这正好是降级该走的形状。

加一条判定:**当前版本是 5.x、所选通道是 stable** 时,返回一份 guidance:

- `title`:说清这是回到 4.x 稳定线,不是普通升级
- `reason`:说清为什么要走安装器(Pilot 内更新只装更高的版本)
- `command`:`INSTALL_COMMAND` 已经默认 stable 通道,直接用;如果要更明确可以带 `--stable`
- `steps`:沿用现有四条(先停服务、`mms web stop`、跑命令、重开 Pilot),**并新增一条**:提醒 5.x 的 Bot 工作台数据不会被 4.x 读取,降级前自己留一份 `~/.local/share/mms-web`

**已验证这条出路是通的**:`install.sh` 在这段(`:1834-1841`)只比对 ref 是否相等,**不做版本大小判断**,所以在 5.1.0 的机器上跑 stable 通道确实会装上 4.23.0。顺带记一笔:它会打印「升级到最新版本: v5.1.0 → v4.23.0」,措辞不对但行为是对的 —— **这行文案不在本包范围**,写进交付即可。

### 3. 把两处承诺改成真话(必须)

一共三处,**全部都要改**(我逐条核对过,在 `main` 和 `dev` 两条线上都还在):

| 文件 | 现在写的 | 问题 |
|---|---|---|
| `apps/mms-web/src/UpdateCenter.tsx:93` | 「切回 4.x 稳定版即可继续留在稳定线」 | 切回通道 ≠ 回到稳定线 |
| `docs/mms-web/CHANGELOG.md:16` | 「把更新通道选成 `5.x 预览版` 或 `4.x 稳定版`,检查更新,确认升级」 | 把双向说成对称的,实际只有 4→5 能走通 |
| `docs/mms-web/RELEASE-v4.22.3.md:11` | 「选回稳定版就继续留在稳定线,**随时可逆**」 | 直接的假承诺 |

`RELEASE-v4.22.3.md` 是历史发布说明,**可以改**:留一句说明这是事后更正即可 —— 让它继续挂着一句假承诺更糟。`CHANGELOG.md` 那条要写清方向性:4.x → 5.x 在 Pilot 内可以走完,5.x → 4.x 需要安装器。

---

## 四、测试

**这个洞能活到今天,是因为没有任何测试断言过跨线时界面说了什么。**

1. **不再说「已是最新」**:构造 `currentVersion = 5.1.0`、`channel = stable`、`latest.tag = v4.23.0`,用 `react-dom/server` 的 `renderToStaticMarkup` 真渲染 `UpdateCenter`,断言输出里**不含**「已是最新」。渲染型测试的写法见 `apps/mms-web/tests/bot-wait-controls.test.mjs:16-22`。
2. **给出了出路**:同一场景下断言渲染结果里出现了安装命令和「复制命令」按钮。
3. **同线时不受影响**:`currentVersion = 4.22.4`、`channel = stable`、`latest.tag = v4.23.0` → 仍然正常显示「发现新版」;`currentVersion = 4.23.0` → 仍然显示「已是最新 4.x 稳定版」。**这条防止修 A 制造 B。**
4. **后端**:`upgrade_guidance()` 在 5.x + stable 时返回 `required: True` 且 `command` 非空;在同线时返回 `None`。
5. **没有自动降级**:断言 `status()` 在 5.x + stable 时 `updateAvailable` 仍然是 `False`、`canUpgrade` 仍然是 `False`。**这条是第二节那个边界的守门人。**

**mutation(每条自己跑,记录红/绿)**:

- 把新增的跨线判断删掉(回到无条件「已是最新」)→ 第 1 条必须红
- 把 guidance 的新分支删掉 → 第 2、4 条必须红
- 把跨线判断写成无条件成立(同线也报跨线)→ 第 3 条必须红
- 把 `available = remote > current` 改成 `remote != current` → 第 5 条必须红

---

## 五、门禁

- 定向 pytest:`tests/test_mms_web_updates.py`、`tests/test_mms_web_update_guidance.py`(若存在)、所有碰 `update_guidance.py` / `updates.py` 的文件。写 base/head 绝对数。
- `apps/mms-web/node_modules/.bin/tsc --noEmit -p apps/mms-web` —— **不要用 `npx tsc`**,仓库根目录会解析到一个同名的假包,会给你假的失败。
- `node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带上**)
- `python3 scripts/ci_pytest_regression.py --base origin/main`
- **改了 `apps/mms-web/src` 就必须在同一个 commit 里重建 `mms_web_static/`**:`npm ci --workspaces=false --ignore-scripts`,然后 `python3 scripts/build_mms_web_release.py --skip-install`。这条没有例外。

---

## 六、边界

- 只改 `mms_web/update_guidance.py`、`apps/mms-web/src/UpdateCenter.tsx`(+ 必要时 `updates.py` 传递线别)、`docs/mms-web/CHANGELOG.md`、`docs/mms-web/RELEASE-v4.22.3.md`,以及重建后的 `mms_web_static/`。
- **不要**动 `available = remote > current`。
- **不要**实现一键降级(见第二节)。
- **不要**动 `install.sh`。
- **不要**碰保护文件:`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`。
- **绝不**碰端口 8767 / 60824 / 8765 / 8766;起验证实例用 61000-62000 的随机端口,**只 kill 自己启动的 PID**,绝不按端口或进程名批量 grep 后 kill,绝不用 `pkill`。
- **绝不**写真实 `~/.config/mms*` 或 `~/.local/share/mms-web`。

## 七、交付

- 提 PR,base 填 `main`,**不要** merge。
- 交付里写清:每条 mutation 的红/绿、门禁实测数、bundle 是否重建、以及第三节第 2 点里 `install.sh` 那行措辞的确认结论(**只写不改**)。
