# T8g — 写锁里还有两个慢调用,最长冻住 Pilot 90 秒

**base**:`main`。两条线同一份代码,修一次回流 `dev`。

**这是第三次了。** 同一个病在这个仓库已经出现三回:

| 版本 | 锁里的慢东西 | 最坏时长 |
|---|---|---|
| v4.18.0 | 文件夹搜索 / 原生选择器 | 对话框开多久锁多久 |
| T8e(本批) | `getfqdn()` 反向 DNS | 实测 30s |
| **T8g(本包)** | **httpx 探测 + 子进程** | **15s / 90s** |

前两次都是机主先在界面上察觉到卡顿才被查出来。这次是审查时提前抓到的,**没有人报过**,但路径和 T8e 完全同构。

---

## 一、证据

`mms_web/server.py` 的 `post()`:

```python
_UNLOCKED_POSTS = (["workspaces", "choose"], ["workspaces", "search"], ["workspaces", "locate"])

def post(self, parts, payload):
    if parts in self._UNLOCKED_POSTS:
        return self._post_readonly(parts, payload)
    with self.mutation_lock:          # ← 下面全部在全局写锁里
        ...
```

白名单只有三条。其余全部持锁。而其中有两条**根本不写任何东西**,却会做网络或子进程调用:

### 1. `POST /configuration/discover` —— 锁内同步 httpx,15 秒

`server.py:444-447` → `mms_web/connections.py:42`:

```python
with httpx.Client(follow_redirects=False, trust_env=False,
                  timeout=httpx.Timeout(15, connect=5)) as client:
    with client.stream("GET", url, headers={...}) as response:
```

用户在「添加模型服务」里点探测模型列表。填的地址如果慢、或者主机不回包,**这 15 秒里 Pilot 的所有 POST 全部排队** —— 发消息、停会话、确认更新、开关远程访问,一起卡住。

而用户填错地址正是这个功能最常见的使用场景。

### 2. `POST /model-settings/{discover,check,refresh}` —— 锁内子进程,90 秒

`server.py:402-403` → `mms_web/model_settings.py:80-82`:

```python
process = subprocess.run(
    [sys.executable, str(Path(__file__).with_name("model_settings_worker.py"))],
    input=..., capture_output=True, env=env, timeout=90)
```

**90 秒。** 比 T8e 那个 30 秒严重三倍。

而这三个动作按它们自己的定义就是只读的 —— `worker(payload)` 调用时**没有 `write=True`**,跑在 `snapshot_config()` 出来的临时快照上;`refresh` 的注释自己写着:

```python
# Reads a capability snapshot and returns proposed edits only. The
# human still reviews them through preview before anything is written.
```

**只读的东西持着全局写锁跑 90 秒。**

### 为什么这次可以放心移出去

和 T8e 不一样 —— T8e 那次我明确说过**不要**把 `set_remote_access` 移出锁,因为它真的在改状态。这两条不是:

- `ModelSettings` **有自己的 `self.lock`**(`discover` / `check` / `refresh` 每个都 `with self.lock:`)。它们之间已经串行,不靠全局锁。
- 它们前后各做一次 `self._check(payload)` 比对 `fingerprint()`,配置在探测期间变了会抛 `CONFIG_STALE`。**并发安全是自己保证的**,不是全局锁给的。
- `configuration/discover` 只把用户填的 URL 打一次,结果直接返回,不落盘。

所以这两条搬出 `mutation_lock` 不会丢任何正确性。这正是 v4.18.0 对文件夹搜索做的事。

---

## 二、要做什么

### 主修(必须)

把这两条加进 `_UNLOCKED_POSTS`,走 `_post_readonly()`:

- `["configuration", "discover"]`
- `["model-settings", "discover"]`、`["model-settings", "check"]`、`["model-settings", "refresh"]`

**注意 `_UNLOCKED_POSTS` 现在是精确列表匹配**(`if parts in self._UNLOCKED_POSTS`),`model-settings` 那三条要分别列出,不要改成前缀匹配 —— `preview` 和 `apply` **必须继续持锁**,它们真的写。这个边界写进注释。

`_post_readonly()` 里现在有个 `if not self.catalog: raise CAPABILITY_UNAVAILABLE` 的兜底,新分支要落在正确的位置,别让它误伤。

### 明确不要做的

- **不要**给 `preview` / `apply` 松锁。它们写配置。
- **不要**把超时改短来"缓解"。15s 和 90s 对各自的工作是合理的;问题是它们在锁里,不是它们慢。
- **不要**顺手重构 `post()` 的分发结构。只加白名单条目 + 分支。
- **不要**碰 `ModelSettings.lock` 或 `fingerprint()` 的语义。

### 顺带(只列不改)

`_UNLOCKED_POSTS` 这种"手工维护的白名单"本身是个隐患:下一个人新增一条慢只读路由时,没有任何东西提醒他。**可以在交付里提一个建议做法**(例如让路由自己声明是否只读),但**不要在这个包里实现**,我来定优先级。

---

## 三、测试

**这个问题活到现在,是因为没有任何测试断言过"哪些路由不持全局锁"。**

1. **锁不被占用(核心)**:patch 掉底层慢调用(`httpx.Client` / `subprocess.run`),让它在被调用时**先去抢 `mutation_lock`**(非阻塞 `acquire(blocking=False)`)并断言抢得到。抢不到就说明调用方还持着锁 —— 测试红。对 `configuration/discover` 和 `model-settings/discover` 各一条。
2. **并发行为**:一个线程发慢的 `model-settings/check`(桩 sleep 若干秒),同时另一个线程发一个普通 POST(例如重命名会话),断言第二个在很短时限内返回,不等第一个。
3. **写路由仍然持锁**:对 `model-settings/apply` 做同样的"抢锁"探测,断言**抢不到** —— 它必须还在锁里。这条防止下一个人图省事把整个 `model-settings` 前缀放出去。
4. **`CONFIG_STALE` 仍然生效**:锁外跑之后,探测期间改动配置仍要抛 `CONFIG_STALE`,不能因为松锁就丢了这层保护。
5. 已有的 `tests/test_mms_web_model_settings.py` 必须全绿,**不许为了这个包放宽它们**。

**mutation(每条自己跑,记录红/绿)**:

- 把 `configuration/discover` 从白名单去掉 → 第 1 条必须红
- 把 `model-settings/discover` 从白名单去掉 → 第 1 条必须红
- 把 `model-settings/apply` **加进**白名单 → 第 3 条必须红
- 把前后两次 `self._check(payload)` 删掉一次 → 第 4 条必须红

---

## 四、门禁

- 定向 pytest:`tests/test_mms_web_model_settings.py`、`tests/test_config_web.py`,以及所有碰 `mms_web/server.py` 的文件。写 base/head 绝对数。
- `python3 scripts/ci_pytest_regression.py --base origin/main`
- `python3 scripts/regression_fresh_user_gate.py`(完整,不加 `--quick`)。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`;并发敏感,串行跑一次。
- 这个包**不碰前端**,如果确实一行 `apps/mms-web/` 都没改,不用重建 bundle —— 在交付里说明。

---

## 五、边界

- **只改 `mms_web/server.py`**(白名单 + `_post_readonly` 分支)。`connections.py` 和 `model_settings.py` 原则上一行不动。
- **不要**碰保护文件:`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`。
- **绝不**碰端口 8767 / 60824 / 8765 / 8766;起验证实例用 61000-62000 的随机端口,**只 kill 自己启动的 PID**,绝不按端口或进程名批量 grep 后 kill,绝不用 `pkill`。
- **绝不**写真实 `~/.config/mms*`;跑测试前确认配置根隔离生效(今天出过一次测试 fixture 写穿真实配置根、把 capability bundle 冲成空壳的事故)。

## 六、交付

- 提 PR,base 填 `main`,**不要** merge。
- 交付里写清:每条 mutation 的红/绿、门禁实测数、以及第二节最后那个"白名单没人守"的建议(**只写不做**)。
