import json
import unittest
from collections import Counter

import redact


class RedactTextTests(unittest.TestCase):
    def check(self, text, label, strict=False):
        counts = Counter()
        out = redact.redact_text(text, counts, strict=strict)
        self.assertIn(f"[REDACTED:{label}]", out)
        self.assertGreaterEqual(counts[label], 1)
        return out

    def test_email(self):
        out = self.check("contact jane.doe@example.com now", "EMAIL")
        self.assertNotIn("jane.doe", out)

    def test_phone(self):
        self.check("call +1 415 555 0142 today", "PHONE")

    def test_aws_key(self):
        self.check("key AKIAIOSFODNN7EXAMPLE used", "AWS_KEY")

    def test_github_token(self):
        self.check("token ghp_abcdefghijklmnopqrstuvwxyz123456 set", "GITHUB_TOKEN")

    def test_secret_assignment_keeps_key_name(self):
        counts = Counter()
        out = redact.redact_text("DB_PASSWORD=hunter2supersecret", counts)
        self.assertIn("DB_PASSWORD=[REDACTED:SECRET_ASSIGNMENT]", out)
        self.assertNotIn("hunter2", out)

    def test_home_path(self):
        out = self.check("saved to /home/jane/runbooks/x.md", "HOME_PATH")
        self.assertNotIn("/home/jane", out)

    def test_ipv4(self):
        self.check("host=10.42.7.19 up", "IPV4")

    def test_generic_token_only_in_strict_mode(self):
        token = "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
        counts = Counter()
        lax = redact.redact_text(f"blob {token} end", counts, strict=False)
        self.assertIn(token, lax)
        strict = redact.redact_text(f"blob {token} end", counts, strict=True)
        self.assertNotIn(token, strict)

    def test_clean_text_untouched(self):
        counts = Counter()
        text = "The deploy succeeded and the healthcheck passed."
        self.assertEqual(redact.redact_text(text, counts), text)
        self.assertEqual(sum(counts.values()), 0)


class RedactMessageTests(unittest.TestCase):
    def test_tool_messages_get_strict_pass(self):
        msg = {"role": "tool", "tool_call_id": "c1",
               "content": "blob a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8 end"}
        out = redact.redact_message(msg, Counter())
        self.assertIn("[REDACTED:GENERIC_TOKEN]", out["content"])

    def test_nested_structures_are_walked(self):
        msg = {"role": "assistant",
               "tool_calls": [{"id": "c1", "arguments": {"to": "jane.doe@example.com"}}]}
        out = redact.redact_message(msg, Counter())
        self.assertEqual(out["tool_calls"][0]["arguments"]["to"], "[REDACTED:EMAIL]")

    def test_round_trips_valid_json(self):
        msg = {"role": "user", "content": "email jane.doe@example.com", "timestamp": 1}
        out = redact.redact_message(msg, Counter())
        self.assertEqual(json.loads(json.dumps(out))["timestamp"], 1)


if __name__ == "__main__":
    unittest.main()
