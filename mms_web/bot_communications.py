"""Durable Bot-to-Bot messages; Pi turns consume a mailbox at idle boundaries."""
from copy import deepcopy
from uuid import uuid4

from .errors import WebError

MAX_COMMUNICATIONS = 5000
MAX_AUTO_HOPS = 8


class BotCommunications:
    def list_communications(self, bot_id, peer_bot_id=None):
        with self._lock:
            self._bot(bot_id)
            if peer_bot_id:
                self._bot(peer_bot_id)
            rows = list(deepcopy(self._communications).values())
            # Project legacy task handoffs without rewriting old evidence.
            for child in self._tasks.values():
                parent = self._tasks.get(child.get("parentTaskId"))
                if not parent:
                    continue
                status = child["status"]
                state = ("processed" if status == "completed" else "failed" if status in {"failed", "cancelled", "interrupted"}
                         else "delivered" if status in {"running", "waiting"} and child.get("sessionId") else "queued")
                rows.append({"id": "dispatch-" + child["id"], "kind": "dispatch", "senderBotId": parent["botId"],
                             "recipientBotId": child["botId"], "content": child["prompt"], "createdAt": child["createdAt"],
                             "taskId": parent["id"], "deliveryTaskId": child["id"], "deliveryStatus": state})
            for task_id, events in self._messages.items():
                parent = self._tasks.get(task_id)
                if not parent:
                    continue
                for event in events:
                    child = self._tasks.get(event.get("childTaskId"))
                    if event["type"] not in {"result", "system"} or not child or child.get("parentTaskId") != task_id:
                        continue
                    text = event["content"]
                    if text.startswith("子任务 " + child["id"]):
                        text = text.split("：", 1)[-1]
                    # A runtime status is a system event, not a result row.
                    kind = "system" if event["type"] == "system" else "result"
                    rows.append({"id": "return-" + event["id"], "kind": kind, "senderBotId": child["botId"],
                                 "recipientBotId": parent["botId"], "content": text, "createdAt": event["createdAt"],
                                 "taskId": child["id"], "deliveryTaskId": parent["id"],
                                 "deliveryStatus": "processed" if parent["status"] == "completed" else "delivered",
                                 "replyTo": "dispatch-" + child["id"],
                                 "artifacts": deepcopy(event.get("artifacts") or []) if kind == "result" else []})
            rows = [r for r in rows if bot_id in {r["senderBotId"], r["recipientBotId"]}
                    and (not peer_bot_id or peer_bot_id in {r["senderBotId"], r["recipientBotId"]})]
            for row in rows:
                if row["deliveryStatus"] == "queued" and not self._bot(row["recipientBotId"])["wakeEnabled"]:
                    row.update(deliveryStatus="waiting", waitReason="autoWakeDisabled")
            return sorted(rows, key=lambda r: (r["createdAt"], r["id"]))

    def send_bot_message(self, task_id, payload):
        from .bots import now, text_field
        with self._lock:
            sender_task = self._task(task_id)
            sender_id = sender_task["botId"]
            key, value = self._replay("communication:" + task_id, payload)
            if key in self._requests:
                return deepcopy(self._communications[value])
            reply_to = payload.get("replyTo")
            original = None
            if reply_to:
                original = next((r for r in self.list_communications(sender_id) if r["id"] == reply_to), None)
                if not original or original["recipientBotId"] != sender_id:
                    raise WebError("BOT_MESSAGE_SCOPE", "只能回复发给当前 Bot 的消息。", 403)
            recipient = original["senderBotId"] if original else str(payload.get("recipientBotId") or "")
            self._bot(recipient)
            if recipient == sender_id:
                raise WebError("BOT_MESSAGE_SELF", "请选择另一只 Bot。", 400)
            content = text_field(payload, "content", 8000, True)
            if len(self._communications) >= MAX_COMMUNICATIONS:
                raise WebError("BOT_MESSAGE_LIMIT", "消息记录已达上限，原记录保留。", 409)
            message_id = "comm_" + uuid4().hex[:16]
            hop = max(int(sender_task.get("messageHop", 0)), int((original or {}).get("hop", 0))) + 1
            row = {"id": message_id, "kind": "message", "senderBotId": sender_id, "recipientBotId": recipient,
                   "content": content, "createdAt": now(), "taskId": task_id, "deliveryTaskId": None,
                   "replyTo": reply_to, "hop": hop,
                   "deliveryStatus": "waiting" if hop > MAX_AUTO_HOPS else "queued",
                   "waitReason": "turnLimit" if hop > MAX_AUTO_HOPS else None}
            self._communications[message_id] = row
            self._remember(key, value, message_id)
            self._persist()
            return deepcopy(row)

    def wake_communication(self, bot_id, message_id):
        with self._lock:
            self._bot(bot_id)
            row = self._communications.get(message_id)
            if not row or row["recipientBotId"] != bot_id:
                raise WebError("BOT_MESSAGE_SCOPE", "只能继续投递发给这个 Bot 的消息。", 403)
            if row["deliveryStatus"] in {"delivered", "processed"}:
                return deepcopy(row)
            if row.get("deliveryTaskId"):
                result = self.wake_task(row["deliveryTaskId"])
                if result["status"] == "queued":
                    row.update(deliveryStatus="queued", waitReason=None)
            else:
                row.update(deliveryStatus="queued", waitReason=None, hop=1, manualWake=True)
            self._persist()
            return deepcopy(row)

    def _deliver_mailbox(self):
        """Called under the runtime lock; receipt and task association persist together."""
        from .bots import now
        changed = False
        for bot in self._bots.values():
            incoming = [r for r in self._communications.values() if r["recipientBotId"] == bot["id"]
                        and r["deliveryStatus"] == "queued" and not r.get("deliveryTaskId")
                        and (bot["wakeEnabled"] or r.get("manualWake"))][:10]
            if not incoming:
                continue
            own_tasks = [t for t in self._tasks.values() if t["botId"] == bot["id"]]
            if any(t.get("orphanAlive") or t["status"] in {"running", "starting"}
                   or t.get("waitReason") in {"approval", "connection", "stopping"} for t in own_tasks):
                continue
            # Reuse unfinished work, so a reply can wake a coordinator waiting for children.
            task = next((t for t in reversed(own_tasks) if t["status"] == "waiting" and t.get("waitReason") in {"user", "children"}), None)
            text = "\n\n".join(f"消息 {r['id']}，来自 {self._bot(r['senderBotId'])['name']}：\n{r['content']}" for r in incoming)
            if task:
                task.update(status="queued", waitReason=None, resumeText=(task.get("resumeText") or "") + "\n\n" + text,
                            updatedAt=now(), acceptedAt=None)
            else:
                if len(self._tasks) >= 2000:
                    for row in incoming:
                        row.update(deliveryStatus="waiting", waitReason="taskLimit")
                    changed = True
                    continue
                task = {"id": "task_" + uuid4().hex[:16], "botId": bot["id"], "prompt": incoming[0]["content"],
                        "originMessageId": incoming[0]["id"], "senderBotId": incoming[0]["senderBotId"],
                        "resumeText": text, "parentTaskId": None, "status": "queued", "runAt": None, "children": [],
                        "result": None, "error": None, "acceptedAt": None, "sessionId": None, "waitReason": None,
                        "turn": 0, "createdAt": now(), "updatedAt": now(), "token": "", "seenEvents": {}}
                self._tasks[task["id"]] = task
                self._messages[task["id"]] = []
                self._artifacts[task["id"]] = []
            task["messageHop"] = max(r["hop"] for r in incoming)
            task["deliveryMessageIds"] = [r["id"] for r in incoming]
            for row in incoming:
                row["deliveryTaskId"] = task["id"]
            changed = True
        return changed

    def _mailbox_receipt(self, task, state):
        for message_id in task.get("deliveryMessageIds", []):
            row = self._communications.get(message_id)
            if row and row["deliveryTaskId"] == task["id"]:
                row["deliveryStatus"] = state
                row["waitReason"] = "execution" if state == "failed" else None

    def _mailbox_prompt(self, task):
        # Ids and real names are supplied by runtime, never inferred by the model.
        rows = [self._communications[mid] for mid in task.get("deliveryMessageIds", []) if mid in self._communications]
        return "\n\n".join(f"消息 {r['id']}，来自 {self._bot(r['senderBotId'])['name']}：\n{r['content']}" for r in rows)
