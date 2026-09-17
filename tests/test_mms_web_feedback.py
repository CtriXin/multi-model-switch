import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from mms_web.errors import WebError
from mms_web.feedback import DAY, FeedbackService, request_surface
from mms_web.server import WebApplication


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = 1800000000
        self.service = self.make_service()

    def tearDown(self):
        self.temp.cleanup()

    def make_service(self, form_url="https://feedback.example.test/form"):
        return FeedbackService(self.root, form_url=form_url, clock=lambda: self.now)

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

    def test_status_does_not_write_usage(self):
        self.assertFalse(self.service.status()["eligible"])
        self.assertFalse(self.service.path.exists())

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

    def test_unconfigured_or_insecure_form_never_invites_or_leaks_invalid_url(self):
        self.medium_use()
        for form_url in ["", "http://feedback.test", "https://user:secret@feedback.test", "https://feedback.test/#secret", "https://[invalid"]:
            service = self.make_service(form_url)
            self.assertFalse(service.status()["enabled"])
            self.assertFalse(service.status()["eligible"])
            self.assertEqual(service.status()["formUrl"], "")

    def test_corrupt_preferences_fail_quietly_without_reprompt(self):
        for text in ["not-json", "[]", '{"schema":1}', '{"schema":2}']:
            self.service.path.write_text(text)
            self.assertEqual(self.service.status()["phase"], "dismissed")
            self.use("new-request")
            self.assertFalse(self.service.status()["eligible"])

    def test_form_open_does_not_claim_a_submission(self):
        self.medium_use()
        status = self.service.invitation({"action": "open"})
        self.assertEqual(status["phase"], "opened")
        self.assertNotIn("received", status)
        self.assertFalse(status["eligible"])
        self.assertEqual(status["formUrl"], "https://feedback.example.test/form")

    def test_config_can_disable_form_without_resetting_preferences(self):
        self.service.invitation({"action": "dismiss"})
        with patch.dict("os.environ", {"MMS_FEEDBACK_FORM_URL": ""}):
            self.assertFalse(FeedbackService(self.root).status()["enabled"])
        self.assertEqual(self.make_service().status()["phase"], "dismissed")

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

    def test_work_and_pending_approvals_block_invites(self):
        self.medium_use()
        with patch("mms_web.server._adapter", return_value=None):
            app = WebApplication(state_root=self.root / "app")
        app.feedback = self.service
        with patch.object(app.bots, "list_tasks", return_value=[{"status": "waiting"}]):
            self.assertFalse(app.get(["feedback"])["eligible"])
            self.assertFalse(app.post(["feedback", "invitation"], {"action": "claim"})["claimed"])
        app.close()


if __name__ == "__main__":
    unittest.main()
