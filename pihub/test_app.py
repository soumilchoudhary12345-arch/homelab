"""Tests for PiHub's core logic. Run: python3 -m unittest pihub/test_app.py"""
import os
import sys
import tempfile
import time
import unittest

NAS = tempfile.mkdtemp(prefix="pihub-test-")
os.environ["PIHUB_NAS"] = NAS
os.environ["PIHUB_DB"] = os.path.join(NAS, "pihub.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app  # noqa: E402

app.init_db()


def reset():
    with app.db() as c:
        for t in ("devices", "files", "rounds", "tasks", "events"):
            c.execute("DELETE FROM " + t)


class SyncRounds(unittest.TestCase):
    def setUp(self):
        reset()
        app.touch_device("laptop")
        app.touch_device("win-pc")

    def test_first_round_queues_every_device(self):
        r = app.sync_round()
        self.assertEqual(sorted(t["device"] for t in r["created"]), ["laptop", "win-pc"])

    def test_not_due_until_interval_passes(self):
        app.sync_round()
        self.assertFalse(app.sync_round()["due"])
        with app.db() as c:
            c.execute("UPDATE rounds SET created = ?", (time.time() - 4 * 86400,))
            c.execute("UPDATE tasks SET status = 'done'")
        self.assertEqual(len(app.sync_round()["created"]), 2)

    def test_no_duplicate_while_one_is_pending(self):
        app.sync_round()
        self.assertEqual(app.sync_round(force=True)["created"], [])

    def test_done_updates_last_sync(self):
        tid = app.sync_round()["created"][0]["id"]
        app.update_task(tid, {"status": "done", "files": 3, "bytes": 99})
        dev = [d for d in app.overview()["devices"] if d["last_sync"]]
        self.assertEqual(dev[0]["last_sync_files"], 3)


class Fetch(unittest.TestCase):
    def setUp(self):
        reset()

    def test_online_source_waits_for_upload(self):
        app.touch_device("win-pc")
        t = app.request_file("win-pc", "Desktop/a.txt", "laptop", "~/Downloads")
        self.assertEqual((t["status"], t["source"]), ("upload_wait", "live"))
        self.assertEqual([x["id"] for x in app.tasks_for("win-pc")], [t["id"]])
        self.assertEqual(app.tasks_for("laptop"), [])

    def test_offline_source_uses_synced_copy(self):
        d = os.path.join(NAS, "devices", "win-pc", "Desktop")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "b.txt"), "w").write("x")
        t = app.request_file("win-pc", "Desktop/b.txt", "laptop", "~/Downloads")
        self.assertEqual((t["status"], t["source"]), ("ready", "stored"))
        self.assertEqual([x["id"] for x in app.tasks_for("laptop")], [t["id"]])

    def test_offline_without_copy_is_an_error(self):
        with self.assertRaises(app.ClientError):
            app.request_file("ghost-pc", "Desktop/c.txt", "laptop", "~/Downloads")

    def test_stored_path_blocks_escape(self):
        for dev, path in (("win-pc", "../../etc/passwd"), ("../x", "a"), ("", "a")):
            with self.assertRaises(app.ClientError):
                app.stored_path(dev, path)


class Inventory(unittest.TestCase):
    def test_index_and_search(self):
        reset()
        d = os.path.join(NAS, "devices", "laptop", "Documents")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "report_2026.pdf"), "w").write("pdf")
        app.index_once()
        hits = app.search("report_")
        self.assertEqual(hits[0]["path"], os.path.join("Documents", "report_2026.pdf"))
        self.assertEqual(app.search("report", device="nobody"), [])


class Agents(unittest.TestCase):
    def test_states(self):
        reset()
        app.add_event({"device": "laptop", "agent": "claude-code", "session": "s1", "event": "PreToolUse", "tool": "Bash"})
        app.add_event({"device": "laptop", "agent": "opencode", "session": "s2", "event": "Notification"})
        states = {s["agent"]: s["state"] for s in app.agent_sessions()}
        self.assertEqual(states, {"claude-code": "running", "opencode": "waiting"})


if __name__ == "__main__":
    unittest.main()
