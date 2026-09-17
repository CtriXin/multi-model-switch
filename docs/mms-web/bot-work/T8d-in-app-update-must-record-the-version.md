# T8d — Pilot 内升级必须记下自己装了什么

**base**:`main`。两条线同一份代码,修一次回流 `dev`。

**这不是推测出来的问题,是机主身上发生过两次的真事故。** 第二次就在今天,我抓了现行。

---

## 一、症状

`~/.config/mms-next/version.json` 是安装元数据的唯一记录:

```json
{
  "installed_ref": "v4.22.4",
  "installed_version": "v4.22.4",
  "install_channel": "stable",
  "release_track": "stable",
  "release_track_version": "4.22.4",
  "release_track_label": "4.x Stable",
  "preferred_language": "zh",
  "installed_at": "2026-09-17T08:49:08Z",
  "source": "install.sh"
}
```

`install.sh` 写它(`install.sh:92` 的 `VERSION_META_PATH="$CONFIG_ROOT/version.json"`,写入在 `:527-557`)。

**Pilot 内升级从不写它。** grep `mms_web/update_install.py` 和 `mms_web/updates.py`,没有任何一处碰 `version.json`。

### 事故一(历史,已被这次安装冲掉)

机主某天从 Pilot 升级到 5.0.x。结果:

- `~/.mms/mms_version.py` → `5.0.1`
- `version.json` → 仍是 `v4.18.0`

今天他跑 `install.sh`,安装器读 `version.json`,于是打印:

```
升级到最新版本: v4.18.0 → v4.22.4
```

**它以为自己在把一台 4.18.0 的机器升到 4.22.4,实际上那台机器跑的是 5.0.1。**

### 事故二(今天,现场抓到)

他在 Pilot 里点了升级到 5.x 预览版,成功装上 5.0.6。我当场读到:

```
~/.mms/mms_version.py            →  5.0.6
~/.config/mms-next/version.json  →  "installed_version": "v4.22.4"
                                    "install_channel": "stable"
                                    "release_track": "stable"
```

代码在 5.0.6 预览线,记录说自己是 4.22.4 稳定线。

---

## 二、后果

1. **`install.sh` 的升级判断建立在错误数据上。** 它据此决定"从哪升到哪"并打印给用户。事故一里它对一次 `5.0.1 → 4.22.4` 的**降级**报告成了 `4.18.0 → 4.22.4` 的升级。文件最后是覆盖对了,但判断依据整个是错的 —— 一旦以后有按版本差做迁移或兼容处理的逻辑,这就是定时炸弹。

2. **通道信息会说谎。** 升级到预览线之后 `install_channel` / `release_track` 还写着 `stable`。任何读这份记录判断"这台机器在哪条线上"的代码或人,都会得到相反的答案。

3. **用户自己也看不出来。** 机主是资深使用者,他都被这个卡住过一次,并且卡了足够久以至于查不出来源。

---

## 三、要做什么

**Pilot 升级成功落地之后,把 `version.json` 更新成实际装上的东西。**

落点在 `mms_web/update_install.py` 的 `install()` 完成之后 —— 那个函数把候选版本的文件复制进安装目录(`FILES` / `GLOBS` / `DIRECTORIES`,注释写明 "Mirrors the copy list in install.sh")。文件都换完了,记录也该跟着换。

### 写什么

按 `install.sh:527-557` 那段的字段形状写,保持一致:

| 字段 | 值 |
|---|---|
| `installed_ref` / `installed_version` | 实际装上的 tag(例如 `v5.0.6`) |
| `install_channel` | 这次升级走的通道:`stable` 或 `preview` |
| `release_track` / `release_track_version` / `release_track_label` | 跟着 tag 和通道算,和 install.sh 的算法一致 |
| `installed_at` | 升级完成时间(UTC,和 install.sh 同格式) |
| `source` | **不要写 `install.sh`** —— 用一个能区分来源的值,例如 `pilot-update`。这样以后排查时一眼能看出这台机器上一次是怎么装的 |

### 绝对不要动的字段

**`preferred_language`。** 这份文件混着两类东西:安装元数据(上面那些)和**用户偏好**(`preferred_language`)。升级只能改前者。把整个文件重写成新字典会静默吃掉用户的语言选择 —— 那是另一个 bug,不要用修 A 的方式制造 B。

**做法**:读出现有 JSON,只覆盖安装元数据那几个 key,其余原样保留,再原子写回。

### 通道从哪来

`UpdateService.channel()` 在 `mms_web/updates.py:158-160`,读的是 `<state_root>/updates/settings.json` 的 `channel` 字段(默认 `stable`,只接受 `stable` / `preview`)。

**注意这是第二份记录**:`updates/settings.json` 的 `channel` 是"我想检查哪条线",`version.json` 的 `install_channel` 是"我实际装的是哪条线"。两者**不是同一件事**,不要合并。举例:用户切到 preview、检查、但没确认升级 —— 此时 channel 是 preview 而实际安装仍是 stable,这个状态是合法的。

所以写 `install_channel` 时,**用这次升级实际装的那个 tag 是不是 prerelease 来判断**,不要直接抄 `channel()` 的返回值。tag 的 prerelease 属性在检查阶段就拿到了(`fetch_preview_release()` 只收 `prerelease=true` 的,`fetch_release()` 走 `/releases/latest` 永远不是 prerelease)。

### 失败怎么办

写 `version.json` 失败**不能让升级失败** —— 文件已经换完了,回滚代价远大于一份记录不准。失败时:记一条可见的日志/系统消息,让用户知道"版本已更新,但安装记录没写成",别静默吞掉。

---

## 四、顺带确认一件事(可能是同一个洞的另一半)

`install.sh` 在 `:93` 还有个 `LEGACY_VERSION_META_PATH="$LEGACY_CONFIG_ROOT/version.json"`。按 "Single Config Root" 规则,`~/.config/mms` 已经退出配置来源。**确认这条 legacy 路径现在是不是死代码**;如果还在被读,那是另一个需要单独处理的问题,**不要在这个包里顺手改**,写进交付说明即可。

---

## 五、测试

**这个 bug 之所以活了这么久,正是因为没有任何测试断言过"升级之后记录和代码一致"。**

至少要有:

1. **端到端**:模拟一次完整的 Pilot 升级(现有测试怎么造候选版本就怎么造),升级后断言 `version.json` 的 `installed_version` 等于装上的 tag、`install_channel` 等于那个 tag 的实际线别。
2. **preview 路径单独一条**:装一个 prerelease tag,断言 `install_channel` / `release_track` 变成 preview 侧的值,而不是留着 stable。
3. **用户偏好不被吃掉**:预置一份带 `preferred_language: "en"` 的 `version.json`,升级后断言它还是 `"en"`。
4. **写入失败不阻断升级**:让写 `version.json` 抛错,断言升级本身仍然成功完成,且有可见的告知。

**mutation(每条自己跑,记录红/绿)**:

- 把新增的写入整段删掉 → 第 1 条必须红
- 把 `install_channel` 写死成 `"stable"` → 第 2 条必须红
- 改成整个文件重写(不保留其余 key)→ 第 3 条必须红
- 让写入失败变成抛出 → 第 4 条必须红

`tests/test_update_install.py` 已经存在,而且它的注释说"当 installer 学会复制新东西而这里没有时会失败" —— 这个包的测试放在同一个文件里最自然。

---

## 六、门禁

- 定向 pytest:`tests/test_update_install.py`、`tests/test_mms_web_updates.py`(如果存在)、以及所有碰到 `update_install.py` / `updates.py` 的测试。写 base/head 绝对数。
- `python3 scripts/ci_pytest_regression.py --base origin/main`
- `python3 scripts/regression_fresh_user_gate.py`(完整,不加 `--quick`)。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`。这个 gate 对并发敏感,串行跑一次,红了单独复跑确认并如实写明。
- 这个包**不碰前端**,如果确实一行 `apps/mms-web/` 都没改,就不用重建 bundle —— 在交付里说明。

---

## 七、边界

- **只改 `mms_web/update_install.py`(以及必要时 `updates.py` 传递 tag 的线别信息)。** 不要改 `install.sh` 的写入逻辑 —— 它是对的,新代码要和它写出同样形状的字段。
- **不要**动 `updates/settings.json` 的 `channel` 语义(见第三节)。
- **不要**碰保护文件:`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`。
- **绝不**写机主真实的 `~/.config/mms-next/**`。测试用临时 config root,并且**跑测试前务必确认隔离生效** —— 今天已经出过一次"测试 fixture 写穿到真实配置根、把 capability bundle 冲成空壳、Pilot 当场瞎掉"的事故,原因就是只清了 `HOME` 而没清对配置根变量。跑测试前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`,并在交付里说明你怎么确认隔离生效的。
- **绝不**碰端口 8767 / 60824 / 8765 / 8766;要起实例用 61000-62000 的随机端口,**只 kill 自己启动的 PID**,绝不按端口或进程名批量 grep 后 kill,绝不用 `pkill`。

## 八、交付

- 提 PR,base 填 `main`,**不要** merge。
- 交付里写清:每条 mutation 的结果、门禁实测数、第四节那个 legacy 路径的确认结论、以及你怎么验证测试的配置根隔离是真的生效。
