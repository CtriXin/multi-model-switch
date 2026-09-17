# T5d 真机验证：计划步骤指定的模型真的生效

同一天、同一脚本、同一组预设，分别打在**修复前的 `dev`**（`9110141d`，worktree `/tmp/t5d-base`，端口 61731）和**修复后的工作树**（端口 61732）上。两边各用独立 `--state-root`（`/tmp/bot-verify-t5d-base`、`/tmp/bot-verify-t5d-head`），`--config-root ~/.config/mms-next` 只读（跑前跑后 `~/.config/mms-next` 文件指纹逐字节相同：`e0f889ce45cab5f7…`）。脚本 `run-verify.py`，原始输出在 `base/` 与 `head/`。

预设（全部来自真实 catalog，非构造）：owner `kimi-for-coding-highspeed`、worker 自己的模型 `deepseek-v4-flash`、计划指定的模型 `glm-5.3`、待生效模型 `MiniMax-M3`。override ≠ worker 默认模型，肉眼可辨（deepseek / glm）。

## 场景

- **A**：worker 先跑一轮普通任务（拿到持久会话）→ 给它写 `pendingPresetId` → 通过**真实计划链路**（`plan-approve` + `POST /tasks/:id/plan {"action":"replace"}`，步骤带 `presetId`）派一步把它交给 worker → 检查那一步实际跑在哪个模型、谁的会话、pending 有没有被吃掉 → 之后再跑一轮普通任务看 pending 是否照旧下一轮生效。
- **B**：另一个 worker（关掉长期记忆）先记一句 `紫色河马在弹钢琴 42`，同样派一步 override → 检查主会话是否被换掉 → 之后普通轮必须仍在**同一个会话**上用**自己的模型**答出那句话。

## 结果对照

| 检查 | base（修复前） | head（修复后） |
|---|---|---|
| 计划步骤要求模型（`presetIdOverride`） | `glm-5.3` | `glm-5.3` |
| 那一步实际生效模型（`task.model` + 会话 `presetId`） | **`deepseek-v4-flash`（错）** | **`glm-5.3`（对）** |
| 那一步用的会话 | worker 主会话 `s-87f6ace0c2b3`（错） | 自己的一次性会话 `s-a0f9750c1419` |
| worker 主会话（`bot.sessionId`） | 被那一步占用 | 不变（`s-5127e497826b`） |
| `pendingPresetId` 是否被 override 轮吃掉 | 没有（保持一致） | 没有 |
| 一次性会话跑完是否已归档 | 无一次性会话 | 已归档（`archived: true`） |
| 下一轮普通任务 | `MiniMax-M3`，新会话 | `MiniMax-M3`，新会话 |
| 场景 B：override 之后的普通轮 | 会话 = 主会话，模型 `deepseek-v4-flash`，答出那句话 | 会话 = 主会话，模型 `deepseek-v4-flash`，答出那句话 |
| `task.reusedSession` 字段 | 不存在（修复前代码） | `false`（一次性会话）/ `true`（续用主会话） |

base 的错误形态与工单一致：**计划要求 `glm-5.3`，实际用 `deepseek-v4-flash` 跑完，而且是在 worker 的主对话里跑的**，界面上没有任何提示。head 的每一步都有真实证据：任务记录 `model`、会话自己的 `presetId`/`modelName`、任务里那条 system 消息“本轮由计划指定使用模型 glm-5.3。”、`reusedSession`。

## 每个文件是什么

- `00-instance.json`：实例端口、版本、四个预设的真实 id/名字。
- `01-scenario-a-step.json`：场景 A 的父任务计划、子任务、worker 记录、子任务消息、子任务会话、主会话、`checks`。
- `02-scenario-a-next-ordinary-round.json`：override 之后那轮普通任务（消费 pending）。
- `03-scenario-b-step.json`：场景 B 的 override 步骤。
- `04-scenario-b-main-conversation-continues.json`：场景 B 的续聊轮（同一会话、自己的模型、从历史里答出原句）。
- `05-session-residue.json`：一次性会话是否被 stop + archive、主会话是否仍然存活、Pilot 侧栏列表。

## 复现方式

```bash
# 修复前
git worktree add --detach /tmp/t5d-base 9110141d
cd /tmp/t5d-base && PYTHONPATH=$PWD python3 -P -m mms_web --port 61731 \
  --state-root /tmp/bot-verify-t5d-base --config-root ~/.config/mms-next --static-root $PWD/apps/mms-web
python3 docs/mms-web/design/t5d/run-verify.py --port 61731 --out <evidence>/base --rev 9110141d ...
# 修复后：同一个脚本换端口与 state-root
```

端口、`--state-root`、`--config-root` 都按包内硬约束：只碰 61000-62000，只 kill 自己启动的 PID，不写真实 `~/.config/mms*`。
