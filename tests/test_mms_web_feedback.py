import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from mms_web.errors import WebError
from mms_web.feedback import DAY, FeedbackService, request_surface
from mms_web.server import WebApplication


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = 1800000000
        self.sent = []
        def sender(endpoint, payload):
            self.sent.append(payload)
            return {"received": True, "receiptId": payload["requestId"]}
        self.sender = sender
        self.service = self.make_service()

    def tearDown(self):
        self.temp.cleanup()

    def make_service(self, endpoint="https://feedback.example.test/submit", sender=None):
        return FeedbackService(self.root, endpoint=endpoint, clock=lambda: self.now, sender=sender or self.sender)

    def use(self, rid, *, bot=False):
        self.service.observe(["bots", "b1", "tasks"] if bot else ["sessions"],
                             {"requestId": rid, "prompt": "private-user-text"}, {})

    def medium_use(self):
        start = self.now
        for day in range(3):
            for visit in range(2):
                self.now = start + day * DAY + visit * 3600
                for turn in range(2):
                    self.use(f"{day}-{visit}-{turn}", bot=bool(turn))
        self.now = start + 3 * DAY

    def form(self):
        return {"requestId": "feedback-request-123", "surface": "bot", "job": "整理工作", "outcome": "partial", "detail": "需要自己复核"}

    def test_get_does_not_write_or_contact_network(self):
        self.assertFalse(self.service.status()["eligible"])
        self.assertFalse(self.service.path.exists())
        self.assertEqual(self.sent, [])

    def test_moderate_usage_all_conditions_and_no_historical_backfill(self):
        for i in range(12):
            self.use(str(i))
        self.now += 4 * DAY
        self.assertFalse(self.service.status()["eligible"])
        self.service.path.unlink()
        self.medium_use()
        self.assertTrue(self.service.status()["eligible"])
        state = self.service.path.read_text()
        self.assertNotIn("private-user-text", state)
        self.assertNotIn("b1", json.dumps(json.loads(state).get("taskIds", [])))
        self.assertEqual(self.sent, [])

    def test_each_medium_usage_threshold_is_required(self):
        self.medium_use()
        original = self.service._read()
        for key, value in [("visits", 5), ("requests", 11), ("days", ["a", "b"]), ("firstAt", self.now - DAY), ("lastAt", self.now - 59)]:
            with self.subTest(key=key):
                self.service.path.write_text(json.dumps({**original, key: value}))
                self.assertFalse(self.service.status()["eligible"])

    def test_retry_and_reading_do_not_inflate_usage(self):
        for _ in range(15): self.use("same-request")
        self.service.observe(["sessions", "s", "stop"], {"requestId": "stop"}, {})
        state = self.service._read()
        self.assertEqual(state["requests"], 1)
        self.assertEqual(state["visits"], 1)

    def test_scheduled_and_peer_work_excluded_but_human_bot_followup_counts(self):
        payload = {"requestId": "r", "prompt": "p"}
        for parts, extra, result in [(["bots", "b", "schedules"], {}, {}), (["bots", "b", "tasks"], {"runAt": "future"}, {}), (["bots", "b", "tasks"], {"parentTaskId": "parent"}, {}), (["bots", "b", "tasks"], {}, {"kind": "schedule"}), (["bot-worker", "tasks"], {}, {}), (["tasks", "t", "dispatch"], {}, {})]:
            self.assertEqual(request_surface(parts, {**payload, **extra}, result), "")
        self.assertEqual(request_surface(["bots", "auto", "tasks"], payload, {}), "bot")
        self.assertEqual(request_surface(["tasks", "t", "messages"], {"content": "followup"}, {}), "bot")

    def test_atomic_claim_and_restart_do_not_repeat(self):
        self.medium_use()
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: self.service.invitation({"action": "claim"}), range(2)))
        self.assertEqual(sum(c["claimed"] for c in claims), 1)
        self.assertFalse(self.make_service().status()["eligible"])
        self.now += 100 * DAY
        self.assertFalse(self.service.status()["eligible"])

    def test_explicit_snooze_at_least_14_days_and_max_two_invites(self):
        self.medium_use()
        self.service.invitation({"action": "claim"})
        self.service.invitation({"action": "later"})
        self.now += 14 * DAY - 1
        self.assertFalse(self.make_service().status()["eligible"])
        self.now += 1
        self.assertTrue(self.service.status()["eligible"])
        self.service.invitation({"action": "claim"})
        self.service.invitation({"action": "later"})
        self.now += 100 * DAY
        self.assertFalse(self.service.status()["eligible"])

    def test_opt_out_survives_new_service_and_more_usage(self):
        self.medium_use()
        self.service.invitation({"action": "dismiss"})
        self.now += 30 * DAY
        self.use("new-request")
        self.assertFalse(self.make_service().status()["eligible"])

    def test_opening_feedback_manually_stops_future_automatic_invitations(self):
        self.service.invitation({"action": "open"})
        self.medium_use()
        self.assertFalse(self.service.status()["eligible"])

    def test_unconfigured_or_insecure_endpoint_never_invites_or_submits(self):
        self.medium_use()
        for endpoint in ["", "http://feedback.test", "https://user:secret@feedback.test", "https://feedback.test/#secret", "https://[invalid"]:
            service = self.make_service(endpoint)
            self.assertFalse(service.status()["enabled"])
            self.assertFalse(service.status()["eligible"])
            with self.assertRaises(WebError): service.submit(self.form())
        self.assertEqual(self.sent, [])

    def test_corrupt_preferences_fail_quietly_without_reprompt(self):
        for text in ["not-json", "[]", '{"schema":1}', '{"schema":2}']:
            self.service.path.write_text(text)
            self.assertEqual(self.service.status()["phase"], "dismissed")
            self.use("new-request")
            self.assertFalse(self.service.status()["eligible"])

    def test_submit_requires_receipt_and_retries_same_id_without_duplicates(self):
        self.medium_use()
        form = self.form()
        self.assertTrue(self.service.submit(form)["received"])
        self.assertTrue(self.make_service().submit(form)["received"])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(set(self.sent[0]), {"requestId", "surface", "job", "outcome", "detail", "recurring", "contact", "campaign", "version", "system"})
        self.assertFalse(self.make_service().status()["eligible"])
        self.assertNotIn("整理工作", self.service.path.read_text())
        with self.assertRaises(WebError): self.service.submit({**form, "detail": "changed"})

    def test_no_success_on_network_error_or_wrong_receipt(self):
        self.medium_use()
        for sender in [lambda *a: {}, lambda *a: {"received": True, "receiptId": "wrong"}, Mock(side_effect=TimeoutError())]:
            service = self.make_service(sender=sender)
            with self.assertRaises(WebError): service.submit(self.form())
            self.assertNotEqual(service.status()["phase"], "submitted")

    def test_unknown_fields_and_long_answers_never_leave_machine(self):
        for extra in [{"transcript": "secret"}, {"endpoint": "https://evil.test"}, {"detail": "x" * 2001}, {"job": ""}, {"surface": "invalid"}]:
            with self.assertRaises(WebError): self.service.submit({**self.form(), **extra})
        self.assertEqual(self.sent, [])

    def test_http_dispatch_observes_accepted_requests_and_excludes_failures(self):
        with patch("mms_web.server._adapter", return_value=None):
            app = WebApplication(state_root=self.root / "app")
        app.feedback = self.service
        with patch.object(app, "_post", return_value={}):
            app.post(["sessions"], {"requestId": "accepted", "prompt": "test"})
        with patch.object(app, "_post", side_effect=WebError("FAILED", "failed", 400)):
            with self.assertRaises(WebError): app.post(["sessions"], {"requestId": "failed", "prompt": "test"})
        self.assertEqual(self.service._read()["requests"], 1)
        # Disk failure must not invalidate an already accepted task.
        with patch.object(app, "_post", return_value={"accepted": True}), patch.object(app.feedback, "observe", side_effect=OSError()):
            self.assertTrue(app.post(["sessions"], {})["accepted"])
        app.close()

    def test_work_and_pending_approvals_block_invites_and_submit_never_holds_app_lock(self):
        self.medium_use()
        with patch("mms_web.server._adapter", return_value=None):
            app = WebApplication(state_root=self.root / "app")
        app.feedback = self.service
        with patch.object(app.bots, "list_tasks", return_value=[{"status": "waiting"}]):
            self.assertFalse(app.get(["feedback"])["eligible"])
            self.assertFalse(app.post(["feedback", "invitation"], {"action": "claim"})["claimed"])
        entered, release = threading.Event(), threading.Event()
        def slow_sender(endpoint, payload):
            entered.set(); release.wait(3)
            return self.sender(endpoint, payload)
        app.feedback.sender = slow_sender
        with ThreadPoolExecutor(max_workers=1) as pool:
            submitted = pool.submit(app.post, ["feedback", "submit"], self.form())
            self.assertTrue(entered.wait(1))
            acquired = app.mutation_lock.acquire(blocking=False)
            self.assertTrue(acquired)
            if acquired: app.mutation_lock.release()
            release.set()
            self.assertTrue(submitted.result()["received"])
        app.close()


if __name__ == "__main__":
    unittest.main()
