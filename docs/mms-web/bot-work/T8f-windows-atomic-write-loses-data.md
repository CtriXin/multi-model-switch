# T8f — Windows 上每一次持久化都可能失败,而且失败是静默的

**base**:`main`。两条线同一份代码,修一次回流 `dev`。

**P0。** 这不是"某个功能不好用",是**用户的会话数据在 Windows 上会丢**,而且丢得无声无息。

---

## 一、证据(用户真机日志,v4.21.14)

```
Traceback (most recent call last):
  File "...\mms_web\server.py", line 610, in do_GET
    return self._json(200, app.get(parts, parse_qs(urlsplit(self.path).query)))
  File "...\mms_web\server.py", line 312, in get
    return self._sessions().get_session(parts[1])
  File "...\mms_web\sessions.py", line 449, in get_session
    runtime = self.runtime_view(session_id) if not session.alive() ...
  File "...\mms_web\session_actions.py", line 84, in runtime_view
    return self._runtime_view_locked(session)
  File "...\mms_web\session_actions.py", line 116, in _runtime_view_locked
    session.persist(self._state_dir)
  File "...\mms_web\sessions.py", line 321, in persist
    private_json(state_dir / f"{self.meta['id']}.json", payload)
  File "...\mms_web\runtime.py", line 157, in private_json
    os.replace(temporary, path)
PermissionError: [WinError 5] 拒绝访问。:
  'C:\Users\EDY\AppData\Local\MMS\mms-web\sessions\.web-ncbnfv5d.tmp'
  -> 'C:\Users\EDY\AppData\Local\MMS\mms-web\sessions\s-c630807daafd.json'
```

**一个会话在保存时失败了。** 用户没有收到任何提示。

---

## 二、根因

`mms_web/runtime.py` 的 `private_json`:

```python
def private_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".web-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(temporary, path)      # ← WinError 5
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)         # ← 把刚写好的数据删掉
```

在 POSIX 上 `rename` 可以覆盖一个正被打开的文件;**Windows 不行**。`os.replace` 拿到 `WinError 5 (Access Denied)` 最常见的原因是:**杀毒软件(包括 Windows Defender)在实时扫描那个刚 close 的临时文件,短暂持有句柄。**

这个持有是**瞬时的** —— 几十毫秒。而 `private_json` 一次都不重试,直接抛。

**这个函数是 Pilot 所有持久化的唯一入口。** 影响面:

| 写什么 | 失败后果 |
|---|---|
| `sessions/*.json` | **会话丢失**(日志里抓到的就是这条) |
| `updates/check.json` | 检查更新永远"没反应"(用户报的症状) |
| `updates/settings.json` | 通道 / 自动检查偏好存不住 |
| `contexts/*.json`、Bot state、artifacts 等 | 同样随机失败 |

### 为什么用户只看到"没反应"

两条路径都把异常吞了:

- **后台线程**:`UpdateService.request_check` 用 `threading.Thread(...daemon=True).start()` 起检查。`check()` 里 `read_json` 之后那段没有外层 `except`,异常直接传播出线程 —— Python 静默丢弃。前端只看到 `checkedAt` 永远是 0,于是文字停在「检查 Pilot 的最新版本」,**而且因为 `error` 也是空的,连红字都没有**。
- **请求线程**:异常变成 500 或连接中断,前端拿不到可读的原因。

---

## 三、要做什么

### 主修:`private_json` 的替换要能扛住瞬时占用(必须)

1. **重试 `os.replace`。** 短退避(例如 10ms / 20ms / 40ms / 80ms / 160ms,总计 ~300ms),只对 `PermissionError` 和 `OSError` 里 Windows 那几个 errno 重试。**不要**无限重试,不要 sleep 到用户能感知。
2. **重试期间不要删临时文件。** 现在的 `finally` 会在失败时 `unlink(temporary)`,把唯一一份完整数据删掉。改成:重试全部失败之后才清理,并且在清理前把失败**明确抛出去**(不要静默成功)。
3. **保持原子性。** **不要**为了绕过这个问题改成"直接写目标文件"—— 那会在断电/崩溃时留下半个 JSON,用一个数据丢失换另一个数据损坏。原子替换的语义必须保留。

### 配套:失败不能再是静默的(必须)

1. **`UpdateService.check()` 要有外层 `except`。** 现在 `read_json` 到 `private_json` 之间任何异常都会逃出线程。捕获之后把真实原因写进 `check.json` 的 `error` 字段(**如果连这个都写不了,就记日志**),让前端那句红字能显示出来。
2. **后台线程的异常必须落到日志。** `request_check` 起的线程、以及 `start_scheduler` 的循环,都要有顶层捕获 + 日志。现在一个 `daemon=True` 的线程抛异常等于什么都没发生。
3. **会话持久化失败要让用户知道。** 这是最要紧的一条:`session.persist()` 失败意味着**这次对话可能没存下来**。至少要记日志;界面上怎么提示由你设计,但"完全不说"是不可接受的。

### 顺带(低优先,不要扩大范围)

日志里大量 `ConnectionAbortedError: [WinError 10053]` 是浏览器关标签页导致的正常断连,不是 bug,但它在刷日志、掩盖真问题。可以在 handler 层把这一类降级成 debug 或直接忽略。**如果做,单独一个 commit**,别和主修混在一起。

---

## 四、测试

**这个 bug 能活到现在,是因为没有任何测试模拟过"替换失败"。**

1. **重试成功**:patch `os.replace`,让它前两次抛 `PermissionError(WinError 5)`、第三次成功。断言 `private_json` 最终成功,文件内容正确,临时文件被清理。
2. **重试耗尽**:让 `os.replace` 一直抛。断言 `private_json` **抛出**(不能静默成功),且临时文件被清理,且**目标文件保持原样**(不是半个文件)。
3. **原子性没被牺牲**:断言实现里没有"直接 open(target, 'w')"这条路径 —— 可以用源码断言,或者构造一个"写到一半失败"的场景断言目标文件未被破坏。
4. **check 不再静默**:让 `private_json` 抛,调 `UpdateService.check(manual=True)`,断言**不抛出到调用方**,且 `status()` 的 `error` 非空(或日志里有记录)。
5. **后台线程异常有日志**:`request_check` 起的线程里抛异常,断言日志里出现了它。

**mutation(每条自己跑,记录红/绿)**:

- 把重试循环去掉(回到单次 `os.replace`)→ 第 1 条必须红
- 把重试耗尽后的 `raise` 去掉(改成静默返回)→ 第 2 条必须红
- 把 `check()` 的外层 `except` 去掉 → 第 4 条必须红
- 把 `finally` 改回"失败也立刻 unlink"→ 第 2 条里"目标文件保持原样"那个断言必须红

---

## 五、真机验证

**必须在 Windows 上验。** 这是 Windows 特有的失败,macOS 上 `os.replace` 不会这样。

- 如果能拿到复现环境:开着 Defender 实时保护,反复创建/切换会话,确认日志里不再出现 `WinError 5`,且 `updates/check.json` 会被正常写出来。
- 如果拿不到真 Windows:用 patch 过的 `os.replace` 在测试里复现全部路径,**并在交付里明写"未在真实 Windows 上验证"**。不要含糊。

用户侧的验收信号很简单:点「检查更新」之后,`%LOCALAPPDATA%\MMS\mms-web\updates\check.json` **应该存在**。现在它不存在。

---

## 六、门禁

- 定向 pytest:所有碰 `mms_web/runtime.py`、`mms_web/updates.py`、`mms_web/sessions.py`、`session_actions.py` 的测试文件。写 base/head 绝对数。
- `python3 scripts/ci_pytest_regression.py --base origin/main`
- `python3 scripts/regression_fresh_user_gate.py`(完整)。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`;并发敏感,串行跑一次。
- **仓库有 Windows CI**(`windows-2022` / `windows-2025` 矩阵,PR 上能看到)。这个包的 PR 必须让那几个 job 绿,而且**如果能在那里加一条覆盖这个路径的测试,优先加** —— 那是我们唯一的真 Windows 执行环境。
- 不碰前端就不用重建 bundle,在交付里说明。

---

## 七、边界

- **主修只改 `mms_web/runtime.py` 的 `private_json`**,配套改 `mms_web/updates.py` 的异常处理。会话持久化的提示如果要动 UI,先说明影响面。
- **不要**把原子写改成直接写。
- **不要**给重试加长 sleep 让用户等。
- **不要**碰保护文件:`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`。
- **绝不**碰端口 8767 / 60824 / 8765 / 8766;起验证实例用 61000-62000 的随机端口,**只 kill 自己启动的 PID**,绝不按端口或进程名批量 grep 后 kill,绝不用 `pkill`。
- **绝不**写真实 `~/.config/mms*`;跑测试前确认配置根隔离生效。

## 八、交付

- 提 PR,base 填 `main`,**不要** merge。
- 交付里写清:mutation 结果、门禁实测数(含 Windows CI 矩阵)、是否在真实 Windows 上验证过、以及第三节"配套"三条各自怎么实现的。
- **这个包合了之后要尽快发版**,Windows 用户现在每一次会话保存都在掷骰子。
