"""Secrets must never reach the agent monitor. Run: python3 -m unittest pihub/client/test_report_event.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from report_event import redact, summarize  # noqa: E402


class Redact(unittest.TestCase):
    def test_header_token(self):
        out = redact('curl -H "X-Token: FAKE-token-for-tests-0000000000" http://pi:8899/api')
        self.assertNotIn("FAKE-token", out)
        self.assertIn("http://pi:8899/api", out)

    def test_key_value_and_bearer(self):
        for s, secret in (("export API_KEY=abc123", "abc123"), ("password=hunter2 login", "hunter2"),
                          ("Authorization: Bearer eyJhbGciOi", "eyJhbGciOi")):
            self.assertNotIn(secret, redact(s), s)

    def test_long_random_strings(self):
        self.assertNotIn("ghp_0123456789abcdefABCDEF0123", redact("echo ghp_0123456789abcdefABCDEF0123"))

    def test_ordinary_commands_survive(self):
        for s in ("python3 -m unittest pihub/test_app.py", "ls -la ~/Documents", "npm run build"):
            self.assertEqual(redact(s), s)

    def test_summarize_uses_redaction(self):
        self.assertNotIn("hunter2", summarize("Bash", {"command": "mysql --password=hunter2"}))


if __name__ == "__main__":
    unittest.main()
