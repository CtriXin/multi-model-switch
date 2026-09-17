# T8e — 打开手机访问会卡住整个 Pilot 30 秒

**base**:`main`(4.22.4 现场复现)。两条线同一份代码,修一次回流 `dev`。

**这不是推测。** 机主在 4.22.4 上报的,我在他机器上把根因测出来了,秒数都对得上。

---

## 一、症状(机主原话 + 截图)

在 Pilot 设置里打开「让手机或另一台电脑访问」:

1. **页面断开**
2. **开关变成不可点击状态**
3. **等一会才打开**,然后才出现地址和二维码

---

## 二、根因,实测

Python 标准库的 `HTTPServer.server_bind` 里有这么一句:

```python
def server_bind(self):
    socketserver.TCPServer.server_bind(self)
    host, port = self.server_address[:2]
    self.server_name = socket.getfqdn(host)   # ← 反向 DNS
    self.server_port = port
```

`socket.getfqdn(host)` 是一次反向 DNS 查询。在机主机器上实测:

```
100.120.8.98     getfqdn -> 'xin-macbook-pro-16.tailf2ca42.ts.net'     0.02s
192.168.23.16    getfqdn -> '192.168.23.16'                           30.00s   ←
127.0.0.1        getfqdn -> '1.0.0.127.in-addr.arpa'                   0.00s
```

**LAN 地址卡 30 秒**,因为他的路由器不响应 PTR 查询 —— 这在家用网络里非常常见,不是他的环境特有。

链条:

1. 点开关 → `WebApplication.set_remote_access`(`mms_web/server.py:217`)
2. → `self.listeners.sync(self.access.extra_binds())`(`:251`)
3. → `sync()` 对每个地址 `ThreadingHTTPServer((address, self._port), self._handler)`(`:728`)
4. → 构造函数里 `server_bind` → `getfqdn("192.168.23.16")` → **阻塞 30 秒**
5. 而 `set_remote_access` 是走 `post()` 的,**它持有 `mutation_lock`**

第 5 条是症状 1 和 2 的来源:那 30 秒里**所有其他 POST 全部排队**,前端的健康轮询超时,于是页面报断开;开关停在 pending 所以变灰。30 秒后绑定返回,一切恢复。

**三个症状、以及"等一会"的实际时长,全部对上。**

### 这和 4.22.2 修的不是同一件事

`RELEASE-v4.22.2.md` 第一条修的是「打开手机访问后,本机 `127.0.0.1` 的窗口不再失效」—— 那是**凭据/token 正确性**问题,做法是切换时给当前连接种下凭据。本包是**阻塞**问题,4.22.2 一行都没碰到。不要把两者混为一谈,也不要去改那次的修复。

### 仓库犯过同一个病

`RELEASE-v4.18.0.md`:「**找文件夹不再冻住整个 Pilot**:这些搜索之前跑在全局写锁里,一次拖拽会让发消息、停会话、确认更新一起排队几秒;原生文件夹选择器更是对话框开多久就锁多久。现在这三条只读路由跑在锁外面。」

当时的解法是把慢路由移出锁。**这次不要照抄那个解法** —— 见第三节。

---

## 三、要做什么

### 主修:绑定时不要做反向 DNS(必须)

`server_name` 只被标准库用来拼 CGI 环境变量,Pilot 从不 emit 这些。所以整个查询是纯浪费。

给监听器一个 `ThreadingHTTPServer` 子类,覆盖 `server_bind` 跳过 `getfqdn`,直接把 `server_name` 设成 host 字符串。`mms_web/server.py` 里**所有**构造 `ThreadingHTTPServer` 的地方都要换成它 —— 至少有两处:`:690` 的主 server 和 `:728` 的每地址监听器。

注释要写明为什么跳过(反向 DNS 在不回 PTR 的网络上阻塞 30 秒,而 `server_name` 我们根本不用),否则下一个人会以为这是可以"顺手清理"的多余覆盖。

### 不要做的:把 set_remote_access 移出 mutation lock

这是 v4.18.0 那次的解法,**这次不适用**。`set_remote_access` 真的在改服务器状态(开关模式、监听集合、token),它**应该**持锁。把一个真正的写操作移出写锁是在拿正确性换延迟。

修掉阻塞之后,绑定本身是毫秒级的,持锁完全没问题。

### 顺带检查:还有没有别的地方会在锁内做网络/DNS

既然查到这里,把 `post()` 的锁内路径扫一遍,看还有没有类似的"看起来是本地操作、实际会发网络请求或做 DNS 解析"的调用。有就列出来,**但不要在这个包里顺手改** —— 写进交付,我来定优先级。

---

## 四、测试

**这个 bug 活到今天,是因为没有任何测试断言过"绑定不做反向 DNS"。**

1. **单元**:把 `socket.getfqdn` patch 成一个会记录调用并 sleep 的桩,构造监听器,断言**它一次都没被调用**。这条是核心。
2. **行为**:`sync()` 绑定一组地址,断言全部进入 `active`,且整个调用在一个很短的时限内完成(用 patch 过的慢 `getfqdn` 来放大差异 —— 没修时会超时,修了之后不会)。
3. **回归**:`_close()` / `close()` 之后端口真的释放,不要因为换了子类而漏掉 `server_close()`。
4. 已有的远程访问测试(token、allowed_hosts、切换后本机窗口仍可用那条 4.22.2 的)必须全绿,**不许为了这个包放宽它们**。

**mutation(每条自己跑,记录红/绿)**:

- 把 `server_bind` 的覆盖删掉(回到标准库实现)→ 第 1 条必须红
- 把子类换回裸 `ThreadingHTTPServer`(只改 `:728` 那处)→ 第 1 条必须红
- 在覆盖里把 `server_close()` 去掉 → 第 3 条必须红

---

## 五、真机验证

必须在**一台反向 DNS 会超时的网络**上验 —— 机主的机器就是(`192.168.23.16` 卡 30 秒,可直接复现)。

验证内容:打开开关 → 页面**不断开**、开关**不长时间变灰**、地址和二维码**立刻出现**;关掉开关 → 监听端口真的释放(`lsof -nP -iTCP -sTCP:LISTEN` 里那两个地址消失)。存证据。

如果你自己的网络反向 DNS 很快(测一下:`python3 -c "import socket,time;t=time.monotonic();socket.getfqdn('<你的 LAN IP>');print(time.monotonic()-t)"`),就用 patch 过的慢 `getfqdn` 在测试里复现,并在交付里说明你没有真实的慢 DNS 环境。

---

## 六、门禁

- 定向 pytest:`tests/` 下所有碰 `mms_web/server.py`、远程访问、监听器的文件。写 base/head 绝对数。
- `python3 scripts/ci_pytest_regression.py --base origin/main`
- `python3 scripts/regression_fresh_user_gate.py`(完整,不加 `--quick`)—— 这个包碰的是服务器启动路径,gate 必跑。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`;它对并发敏感,串行跑一次,红了单独复跑确认并如实写明。
- 这个包**不碰前端**,如果确实一行 `apps/mms-web/` 都没改,不用重建 bundle —— 在交付里说明。

---

## 七、边界

- **只改 `mms_web/server.py`**(监听器子类 + 两处构造点)。
- **不要**动 `mms_web/remote_access.py` 的模式语义 —— `bind_address()` 那段注释("lan does not widen this socket")是对的,主 socket 本来就不该随开关变。
- **不要**动 4.22.2 那次的凭据修复。
- **不要**把 `set_remote_access` 移出 mutation lock(见第三节)。
- **不要**碰保护文件:`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`。
- **绝不**碰端口 8767 / 60824 / 8765 / 8766;起验证实例用 61000-62000 的随机端口,**只 kill 自己启动的 PID**,绝不按端口或进程名批量 grep 后 kill,绝不用 `pkill`。
- **绝不**写真实 `~/.config/mms*`;跑测试前确认配置根隔离生效(今天刚出过一次测试 fixture 写穿真实配置根、把 capability bundle 冲成空壳的事故)。

## 八、交付

- 提 PR,base 填 `main`,**不要** merge。
- 交付里写清:mutation 结果、门禁实测数、真机验证的网络条件(反向 DNS 是否真的慢)、第三节那个"锁内还有没有别的网络调用"的扫描结论。
