import unittest

from gitgen.safe_mode import DiffReport, is_sensitive_file, mask_text, prepare_diff


def make_diff(path: str, lines: int) -> str:
    body = "".join(f"+line {i}\n" for i in range(lines))
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{lines} @@\n{body}"


class MaskingTest(unittest.TestCase):
    def test_masks_api_key_email_and_secret_assignment(self):
        report = DiffReport()
        text = mask_text(
            '+key = "sk-abcdefghijklmnop1234"\n+mail: user@example.com\n+PASSWORD = "hunter2pass"\n',
            report,
        )
        self.assertNotIn("sk-abcdefghijklmnop1234", text)
        self.assertNotIn("user@example.com", text)
        self.assertNotIn("hunter2pass", text)
        self.assertIn("PASSWORD = \"[MASKED_SECRET]\"", text)
        self.assertEqual(report.masked_total, 3)

    def test_sensitive_files_detected(self):
        self.assertTrue(is_sensitive_file("config/.env"))
        self.assertTrue(is_sensitive_file("certs/server.pem"))
        self.assertFalse(is_sensitive_file("gitgen/cli.py"))


class LimitTest(unittest.TestCase):
    def test_safe_mode_limits_files_and_lines(self):
        diff = "".join(make_diff(f"f{i}.py", 30) for i in range(15))
        text, report = prepare_diff(diff, safe_mode=True, max_files=10, max_lines=200)
        self.assertEqual(report.files_total, 15)
        self.assertLessEqual(report.files_sent, 10)
        self.assertLessEqual(report.lines_sent, 200)
        self.assertIn("줄 수 제한", text)

    def test_safe_mode_excludes_env_file(self):
        diff = make_diff(".env", 2) + make_diff("app.py", 2)
        text, report = prepare_diff(diff, safe_mode=True)
        self.assertEqual(report.excluded_files, [".env"])
        self.assertNotIn("a/.env", text)

    def test_without_safe_mode_diff_is_untouched(self):
        diff = make_diff("app.py", 5) + "+mail user@example.com\n"
        text, _ = prepare_diff(diff, safe_mode=False)
        self.assertEqual(text, diff)

    def test_char_limit_always_applies(self):
        text, report = prepare_diff(make_diff("big.py", 2000), safe_mode=False, max_chars=500)
        self.assertTrue(report.truncated_chars)
        self.assertLess(len(text), 600)


if __name__ == "__main__":
    unittest.main()
