import json
import unittest

import trace_lint


def lines(*messages):
    return [json.dumps(m) for m in messages]


class LintTests(unittest.TestCase):
    def test_clean_trace(self):
        turns, errors, warnings = trace_lint.lint_lines(lines(
            {"role": "user", "content": "hi", "timestamp": 1},
            {"role": "assistant", "content": "hello", "timestamp": 2},
        ))
        self.assertEqual(turns, 2)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_invalid_json_line(self):
        _, errors, _ = trace_lint.lint_lines(["{not json"])
        self.assertTrue(any("invalid JSON" in e for e in errors))

    def test_missing_role(self):
        _, errors, _ = trace_lint.lint_lines(lines({"content": "hi"}))
        self.assertTrue(any("missing role" in e for e in errors))

    def test_consecutive_same_role_warns(self):
        _, _, warnings = trace_lint.lint_lines(lines(
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
        ))
        self.assertTrue(any("consecutive" in w for w in warnings))

    def test_dangling_tool_call(self):
        _, errors, _ = trace_lint.lint_lines(lines(
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c9", "name": "exec"}]},
        ))
        self.assertTrue(any("dangling tool call" in e and "c9" in e for e in errors))

    def test_resolved_tool_call_is_clean(self):
        _, errors, _ = trace_lint.lint_lines(lines(
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c9", "name": "exec"}]},
            {"role": "tool", "tool_call_id": "c9", "content": "ok"},
        ))
        self.assertEqual(errors, [])

    def test_backwards_timestamp(self):
        _, errors, _ = trace_lint.lint_lines(lines(
            {"role": "user", "content": "a", "timestamp": 10},
            {"role": "assistant", "content": "b", "timestamp": 5},
        ))
        self.assertTrue(any("timestamp goes backwards" in e for e in errors))

    def test_min_turns_enforced(self):
        _, errors, _ = trace_lint.lint_lines(lines(
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ), min_turns=150)
        self.assertTrue(any("minimum required is 150" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
