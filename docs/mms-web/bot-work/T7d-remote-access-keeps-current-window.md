# T7d · 开手机访问不该把当前这个窗口踢掉

Date: 2026-09-16
Task: Stride 370e87ec37e741df
建议模型：k3 / deepseek（后端为主，前端只有一句文案）
来源：owner 2026-09-16——在设置里打开「手机访问」开关，出现二维码和局域网地址之后，本机原本开着的 `127.0.0.1` 窗口立刻失效，必须带 token 参数才能再进去

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、`docs/mms-web/REMOTE-ACCESS.md`、本文件，然后按下面"要读的代码"逐处确认。

**本包与 T7c 互相独立，可以并行。** 改动面零重叠：T7d 只动 `mms_web/server.py` 的 `set_remote_access` / 响应头链路与 `RemoteAccess.tsx`；T7c 只动 `model_settings_worker.py` 加一个新模块和 `ChannelModels.tsx` 的渲染核对。两个包没有任何共享文件。

---

## base 分支判定（2026-09-16 实测）

### 结论

| 项目 | 分支 | 依据 |
| --- | --- | --- |
| **实现 PR 的 base** | **`main`（4.22.1，`6c62a656`）** | 本包要改的**语义**在两条线上完全一致（见下面的差异说明）；owner 定的流向是"4.x 的所有改动默认进入 5.x" |
| 本工作包文档所在分支 | `dev`（5.x，`e5d32243`） | `docs/mms-web/bot-work/` 整棵树**只存在于 `dev`** |

### 实测证据与**一处必须说明的差异**

owner 指定的那条 diff，实际结果：

```
 apps/mms-web/src/SettingsPage.tsx | 138 ++++++++++++++++++++++++++++++++------
 mms_web/server.py                 | 117 ++++++++++++++++++++++++++++++--
 2 files changed, 231 insertions(+), 24 deletions(-)
```

| 文件 | main | dev | 判定 |
| --- | --- | --- | --- |
| `mms_web/remote_access.py` | `d626c54e` | `d626c54e` | **逐字节相同** |
| `apps/mms-web/src/RemoteAccess.tsx` | `7855ec24` | `7855ec24` | **逐字节相同** |
| `apps/mms-web/src/api.ts` | `5ba09216` | `5ba09216` | **逐字节相同** |
| `tests/test_mms_web_remote_access.py` | `7c120f85` | `7c120f85` | **逐字节相同** |
| `tests/test_mms_web_lan_switch.py` | `a2ff4726` | `a2ff4726` | **逐字节相同** |
| `mms_web/server.py` | `cbcb9855` | `f9c3c5a3` | **有差异，见下** |

**`server.py` 的差异逐条核对过，结论是：本包要改的四个位置（`set_remote_access`、`_send`、`_json`、`do_POST` 的收尾）在两条线上代码完全一致，只是行号整体下移。** 117 行差异全部是 5.x 的 Bot 工作台接线：

- `WebApplication.__init__` 构造 `BotRuntime` / `PiBotExecutor` / `EgoComputer`
- `_visible_sessions` 过滤掉 Bot 拥有的会话
- `get()` / `_post()` 里的 `/bots`、`/tasks`、`/update/history` 路由
- CSP 里 `img-src` 加 `blob:`、新增 `frame-src 'self' blob:` 与 `media-src 'self' blob:`
- `do_GET` 里 Bot 成果预览的两条分支
- **`do_POST` 多了 `bot-worker` 内部接口分支**，收尾那行从
  `self._json(200, app.post(self._parts(), payload))`（main 644）
  变成
  `self._json(200, app.bots.worker(worker_id, payload) if worker else app.post(parts, payload))`（dev 749）
- `create_server` 末尾多两行 `app.bots.configure_endpoint(...)` / `app.bots.start()`

**对本包唯一有实际影响的是最后那条 `do_POST` 收尾行**：如果实现者选了方案 B（在 `do_POST` 里特殊处理这条路由，见"怎么给这条 JSON 响应挂 header"），那么这一行在 4.x→5.x 合流时**会冲突**，合的时候要保留 5.x 的 `worker` 分支、把 remote-access 的处理套在 `app.post(parts, payload)` 这一侧。**这一点必须写进实现者的交付。** 选方案 A（给 `_send` / `_json` 加可选 `headers` 参数）则不碰这一行，没有冲突面。

---

## 症状

用户在设置里打开「手机访问」开关，出现二维码和局域网地址之后，**本机原本开着的 `127.0.0.1` 窗口立刻失效**，必须带 token 参数才能再进去。owner 的预期是：只有局域网地址需要令牌，当前开着的窗口不该被踢掉。

## 根因

三处，缺一不可。行号 **main / dev 两列都列出**（owner 给的是 dev 的，全部复核吻合）：

| # | 位置 | main | dev | 代码 |
| --- | --- | --- | --- | --- |
| 1 | `WebApplication.set_remote_access()` | **203** | 231 | 把模式切成 `lan`（`self.access.set_mode(wanted)`，main **235** / dev **263**），**把 token 放进返回的 JSON**（`access.state()` 的 `"token"` 字段，`remote_access.py:261`），但**没有给当前这个请求种 cookie** |
| 2 | `Handler._gate()` | **564-592** | 650-678 | `if not app.access.required: return True`（main **573** / dev **659**）—— 一旦 `required` 为真就**无差别**校验每个连接，loopback 也不例外 |
| 3 | 全局唯一一处 `Set-Cookie` | **586-588** | 672-674 | 在 `_gate()` 里，**只有当 token 从 query string 进来、且是 GET 时才发**（`if from_query and self.command == "GET"`，main **581** / dev **667**） |

链路：点开关 → `set_mode("lan")` → `_apply()` 生成 token → `access.required` 变真（`remote_access.py` 的 `required` = `bool(self.token)`）→ 当前窗口下一个请求既没有 cookie 也没有 query token → `_gate()` 返回 401。

顺带确认了两件事：

- `remote_access_state()`（main **185** / dev **213**）返回的 `state` 里**确实带着明文 token**（`remote_access.py:256-266` 的 `state()`），所以"这个响应知道 token"不是问题，缺的只是把它写成 cookie。
- `apps/mms-web/src/api.ts:29` 是 `credentials: "same-origin"`，**浏览器会自动接收并保存同源响应的 `Set-Cookie`，后续请求自动带上**。所以前端**不需要**为 cookie 本身写任何代码。

---

## 已定的设计决策，不要改

**不许放行 loopback，不许改 `_gate()` 那条无差别校验。**

`server.py` main **571-572** / dev **657-658** 的注释写明了理由：

```python
# A tunnel can reach this socket over loopback without forwarding
# headers. Remote mode therefore authenticates every connection.
```

隧道（ngrok、cloudflared 之类）是连到 `127.0.0.1` 这个 socket 上的，所以"请求来自 loopback"**并不能证明它是本机的人**——外网经隧道进来的请求长得一模一样。放行 loopback 会在隧道场景下开一个真洞。

这条安全性质已经有回归测试守着，实现者动之前先读：

- `tests/test_mms_web_remote_access.py:152` `test_remote_mode_requires_a_token_even_without_forwarding_headers`
- `tests/test_mms_web_remote_access.py:161` `test_a_tunnel_also_arrives_from_loopback_and_is_not_exempt`

**这条性质必须原样保住。** 写在这里就是为了防止实现者"顺手简化"成 `if client_address == 127.0.0.1: return True`。

**正确修法：开关打开时，在那个响应上给当前会话种 cookie。** 点开关的这个会话在切换之前就已经通过 loopback 授权了（而且这是个 POST，已经过了 `_check_origin(mutation=True)` 的 Host / Origin / `Sec-Fetch-Site` / CSRF 四道检查），给它 cookie 等价于它自己去点一次带 token 的链接——**不多给任何权限，其他连接照样要令牌**。

---

## 怎么给这条 JSON 响应挂 header（**实现上的坑，已实测查清**）

`set_remote_access` 是一个**返回 dict 的普通 JSON handler**，响应由通用路径写出：

```
do_POST (main 623-646 / dev 718-751)
  └─ self._json(200, app.post(parts, payload))        main 644 / dev 749
       └─ _json(status, payload)                      main 544 / dev 630
            └─ _send(status, body, content_type, *, preview=False)   main 524 / dev 609
                 send_response → 九个写死的 send_header → end_headers → wfile.write
```

`_send` 的签名是 `def _send(self, status, body, content_type, *, preview=False)`，**只有 `preview` 一个开关，没有任何加 header 的口子**。`app.post()` 返回的 dict 直接进 `json.dumps`，**协议层拿不到 handler 的任何额外意图**。所以现状是：**没有现成的办法往这条响应上挂 header。**

三条路，实现者**必须明确选一条并在交付里说明选了哪种、为什么不影响别的接口**：

### 方案 A：给 `_send` / `_json` 加可选 `headers` 参数（推荐）

```python
def _send(self, status, body, content_type, *, preview=False, headers=()):
    ...
    for name, value in headers:
        self.send_header(name, value)
```

`do_POST` 里判断这条路由需要 cookie 时传进去。

- 优点：不碰 `do_POST` 那行在两条线上不同的收尾语句，**4.x→5.x 合流无冲突**；对所有现有调用点零影响（默认空）。
- 代价：改了一个被 `_json` / `_error` / `do_GET` 多处调用的公共方法。默认值必须是空，且**必须补一条断言：不传 `headers` 时响应头与改动前逐条一致**。
- ⚠️ `_send` 在 `mms_web/server.py` 里，虽然不在受保护文件清单上，但它是所有 HTTP 响应的唯一出口。**只允许追加，不允许重排既有的九个 `send_header` 调用顺序，不允许改任何既有 header 的值。**

### 方案 B：在 `do_POST` 里特殊处理这一条路由

拿到 `app.post(parts, payload)` 的结果后，若 `parts == ["remote-access"]` 且此刻 `app.access.required` 为真，就直接 `send_header` 一条 Set-Cookie。

- 优点：影响面最小，`_send` 一个字不改。
- 代价：**`do_POST` 的收尾行在 main 和 dev 上不同**（见上面 base 判定），合流会冲突；而且要么绕过 `_json` 自己写响应（重复一遍九个 header，容易漏），要么还是得改 `_send`。

### 方案 C：在 `WebApplication` 上挂一个"待发 header"的可变字段

**禁止。** `create_server` 用的是 `ThreadingHTTPServer` + `daemon_threads = True`（main **650-651** / dev **755-756**），`app` 是所有线程共享的单例，**一个可变的 pending-header 字段会在并发请求之间串**——可能把 token cookie 发给另一个正在请求的连接。这是个真的安全洞，不是洁癖问题。写在这里就是为了挡掉它。

---

## 要做成什么

### A. 打开开关时种 cookie

`set_remote_access` 在**打开**远程访问成功后（`enabled: true` 那条路径，走到 main 235 / dev 263 的 `set_mode(wanted)` 之后），给这次响应加 `Set-Cookie`。

**cookie 的形状必须和 `_gate()` 里那处完全一致**，不要另写一套：

```python
f"{access.COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000"
+ ("; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else "")
```

（`access.COOKIE` = `"mms_pilot_key"`，`remote_access.py:25`；`Max-Age=31536000`；`Secure` 的判定见 main **585** / dev **671**。）

**最好的做法是把这个字符串的构造抽成一个共用的小函数，两处都调它**，这样形状不可能再分叉。抽函数时不要改 `_gate()` 那处的行为。

### B. `regenerate`（换 token）是同一个成因的第二个入口

换完之后旧 token 全部失效，**包括当前这个窗口**——用户点「换一个 token」就把自己锁在门外了。`set_remote_access` 的 `regenerate` 分支（main **216-220** / dev **244-248**）同样要给当前会话重新种 cookie，用同一个函数。

现有测试 `tests/test_mms_web_lan_switch.py:96` `test_a_regenerated_token_rejects_the_old_one` 守的是"旧 token 失效"，**那条必须继续通过**——新 cookie 带的是新 token，两件事不冲突。

### C. 不要顺手改的路径

- **关闭开关（回 `loopback`）**：token 清空（`remote_access.py` 的 `_apply()` 把 `self.token` 置 `""`）、`required` 变假、`_gate()` 直接放行。本来就没问题，**不要动**。也不要顺手去清 cookie——留着的 cookie 在 `required` 为假时根本不会被读，清它没有收益，反而可能影响 `test_turning_it_off_and_on_keeps_the_same_link_working`（`lan_switch.py:85`）。
- `hostname` / `removeHostname` 两个分支（main **206-215** / dev **234-243**）不涉及 token 变化，不要动。
- `mode == "all"` 那条提前返回（main **233-234** / dev **261-262**）不要动。

### D. 前端一句文案

`apps/mms-web/src/RemoteAccess.tsx`（244 行，两线逐字节相同）第 **104** 行现在写的是：

```
带 token 的链接才能打开。共用网络里，同网段的人也能碰到这个入口。
```

要说清楚：**开启后本机地址也需要令牌，当前窗口会自动保持登录**。文案不要吓人，但要让用户知道**别的本机窗口/标签页需要用新链接重新进**。

同时第 **146** 行「换一个 token」按钮的 `title` 现在是「之前发出去的链接和已打开的页面都会失效」，第 **154** 行的 `section-note` 是「换 token 会让之前发出去的链接全部失效。」——**这两句在 B 做完之后就不准确了**（当前这个窗口不会失效），要一并改准。

### E. 文档订正

`docs/mms-web/REMOTE-ACCESS.md` 第 **18** 行：

> 关掉后这些入口立刻关闭，网络上再也看不到；本机那个入口不受影响，一直在。

「本机那个入口不受影响」在 token 门禁这件事上**是错的**（socket 确实一直在，但开启后本机也要过 token）。第 **34-37** 行的 token 小节也要补一句"开关打开时，正在操作的这个窗口会自动拿到令牌"。

---

## 只许改

- `mms_web/server.py`：`set_remote_access` 的两条分支、cookie 形状的共用函数、以及方案 A/B 里选中的那一处挂 header 的机制
- `apps/mms-web/src/RemoteAccess.tsx`：104、146、154 三处文案
- `tests/test_mms_web_remote_access.py` 或新增 `tests/test_mms_web_remote_access_cookie.py`
- `docs/mms-web/REMOTE-ACCESS.md`：18 行与 token 小节

## 不许改

- **`_gate()` 那条无差别校验的语义**（main 573 / dev 659 的 `if not app.access.required`）。不许加 loopback 例外，不许加 `client_address` 判断，不许加任何形式的"本机豁免"。
- `mms_web/remote_access.py`（`RemoteAccess` 类、token 生成与存储、`state()`、`links()`）——本包不改 token 的产生和语义，只改"谁在什么时候拿到它"。
- 关闭开关那条路径、`hostname` / `removeHostname` 分支、`mode == "all"` 提前返回。
- `_send` 里既有九个 `send_header` 的顺序和值；CSP、`X-Frame-Options`、`X-MMS-*` 一律不动。
- `_check_origin` 的四道检查。
- 受保护文件（`mms_core.py` / `mms_launchers.py` / `mms_tui.py` / `mms_bridge.py` / `mms_account_state.py` / `mms_session.py` / `mms_adapter_registry.py` / `mms` / `ccs`）。
- 真实 `~/.config/mms*`。
- 端口 **8767** 和 **60824**，以及 `.worktrees/main-4.22`。

---

## 硬验收项

这四条是本包的核心，**每条都要有 Python 单测**：

- [ ] **①** 开启开关后当前窗口继续可用，不需要手动带参数。
      构造：loopback 下 `POST /api/v1/remote-access {"enabled": true}` → 断言响应带 `Set-Cookie`，值等于 `access.token`，且含 `Path=/`、`HttpOnly`、`SameSite=Lax`、`Max-Age=31536000` → 带这个 cookie 再 `GET /api/v1/sessions` 得 **200**。
- [ ] **②** 同一台机器上**另开**一个没有 cookie 的 `127.0.0.1` 标签页仍然 **401**。
      **这是防止实现者为了省事把 loopback 放行的回归门禁，必须写，必须显式断言 401。** 参考 `tests/test_mms_web_remote_access.py:36` 的 `fetch()` helper（它已经支持 `cookie=` 和 `remote=` 参数）。
- [ ] **③** 换 token 后当前窗口仍可用，而用旧 token 的链接失效。
      构造：开启 → 记下 `old = access.token` → `POST {"regenerate": true}` → 断言响应带新 token 的 `Set-Cookie` → 带**新** cookie 请求 200，带 `old` 请求 **401**。
- [ ] **④** 关闭开关后一切恢复原状：`POST {"enabled": false}` → `access.required` 为假 → 不带任何 cookie 的 loopback 请求 **200**。
- [ ] `X-Forwarded-Proto: https` 时 cookie 带 `Secure`，不带该头时不带 `Secure`（两处 cookie 形状一致的证明）
- [ ] 方案 A 的话：不传 `headers` 时 `_send` 的响应头与改动前逐条一致，有断言

## 浏览器实测

用 **ego-browser** 做一次真实验证（`/Users/xin/.agents/rules/browser-default.md`）：

- **自己另起端口**（例如 61707），**不要动 8767 和 60824**
- 用临时 state-root / config-root，**不要写真实 `~/.config/mms*`**
- 走一遍：开关打开前的本机页面 → 打开开关 → **不刷新也不带参数，直接在当前窗口继续操作**（切个 tab、读一次设置） → 另开一个无 cookie 的隐身窗口访问同一地址看到 401 → 换 token → 当前窗口继续可用 → 关闭开关
- 每一步截图存 `docs/mms-web/design/t7d/`
- 用完关掉自己起的那个实例，**不要重启任何已有 Pilot 实例**

## 门禁

**实测基线**（2026-09-16，两条线各跑一遍）：

| 门禁 | `origin/main` = `6c62a656` = 4.22.1 | `origin/dev` = `e5d32243` = 5.x |
| --- | --- | --- |
| `PYTHONPATH=. python3 -m pytest -q tests/test_mms_web_remote_access.py tests/test_mms_web_lan_switch.py tests/test_mms_web_model_settings.py tests/test_config_web.py` | **204 passed / 2 failed / 3 skipped** | **204 passed / 2 failed / 3 skipped** |
| `npx tsc --noEmit -p apps/mms-web` | **0 错** | **0 错** |
| `node --test apps/mms-web/tests/*.test.mjs` | **tests 56 / pass 56 / fail 0** | **tests 121 / pass 121 / fail 0** |
| `npm run build --workspace @mms/web` | 通过，css 148.95 kB / js 660.01 kB | 通过，css 223.13 kB / js 793.19 kB |

⚠️ **那 2 个 failed 是两条线上都已存在的既有失败，与本包无关**，不许当成自己引入的，也不许顺手去修：

```
FAILED tests/test_config_web.py::test_config_web_model_capability_defaults_are_profile_backed_not_hardcoded
FAILED tests/test_config_web.py::test_config_web_provider_model_fetch_returns_policy_capabilities
```

两条都是 `assert caps["reasoning"] is True` 失败（`test_config_web.py:4563` 一带），属于 model capability profile 的既有问题。**本包的门禁标准是：这个数字不变，且这两条仍然是唯一的 failed。**

本包必跑：

```bash
PYTHONPATH=. python3 -m pytest -q \
  tests/test_mms_web_remote_access.py tests/test_mms_web_lan_switch.py \
  tests/test_mms_web_server.py tests/test_mms_web_plain_http_origin.py
npx tsc --noEmit -p apps/mms-web
node --test apps/mms-web/tests/*.test.mjs      # 必须带 *.test.mjs glob
npm run build --workspace @mms/web
```

覆盖 remote access 的测试文件，实现者已知的入口是 `tests/test_mms_web_remote_access.py`（**14** 个测试，含 `_gate` 与 cookie 的现有断言）与 `tests/test_mms_web_lan_switch.py`（**37** 个测试，含开关 / regenerate / 端口）。改了 `_send` 的话 `tests/test_mms_web_server.py` 与 `tests/test_mms_web_plain_http_origin.py` 也要跑。实现者需自己确认是否还有别的文件覆盖到这条链路，并把最终清单写进交付。

`node --test apps/mms-web/tests/` **不带 glob 会直接报 `fail 1`**（README 已记录，2026-09-16 实测）。跑前端门禁之前先在 worktree 里 `npm install`。

## 交付必须写明

除通用验收外，额外要写：

- 选了 A / B 哪个方案挂 header，为什么，以及**不影响别的接口**的依据
- 选 B 的话，`do_POST` 收尾行在 4.x→5.x 合流时怎么合（保留 5.x 的 `worker` 分支）
- 硬验收 ② 的测试函数名和实际断言（这是本包最重要的一条）
- ego-browser 用的端口、截图路径、实例是否已关闭

## 并行规则

```
git worktree add ../wt-T7d -b bot/T7d-remote-access-cookie origin/main
```

自己另起端口，**不碰 8767 和 60824**，不动 `.worktrees/main-4.22`。不提交、不 push、不 merge，等 owner 验收。
