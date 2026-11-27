import unittest

from gitgen.validator import (
    fix_pr_body, normalize_title, truncate_title, validate_commit, validate_pr,
)

GOOD_BODY = "## Why\n- 배경\n\n## What\n- 변경\n\n## How to Test\n- `python main.py pr`"


class CommitValidationTest(unittest.TestCase):
    def test_should_pass_conventional_title_with_bullets(self):
        result = validate_commit("feat(cli): 커밋 메시지 생성 명령 추가\n\n- cli.py: commit 명령 추가")
        self.assertTrue(result.ok, result.errors)

    def test_should_reject_title_over_72_chars(self):
        result = validate_commit("feat: " + "가" * 80)
        self.assertFalse(result.ok)

    def test_should_warn_title_over_50_chars(self):
        result = validate_commit("feat: " + "a" * 50)
        self.assertTrue(result.ok)
        self.assertTrue(any("권장" in w for w in result.warnings))

    def test_should_reject_body_without_bullets(self):
        result = validate_commit("fix: 오류 처리 개선\n\n그냥 문장입니다.")
        self.assertFalse(result.ok)

    def test_should_reject_vague_title(self):
        self.assertFalse(validate_commit("fix: update files").ok)


class PrValidationTest(unittest.TestCase):
    def test_should_pass_full_template(self):
        self.assertTrue(validate_pr("feat: PR 초안 생성", GOOD_BODY).ok)

    def test_should_reject_missing_section(self):
        result = validate_pr("feat: PR 초안 생성", "## Why\n- 배경\n\n## What\n- 변경")
        self.assertIn("PR 본문에 '## How to Test' 섹션이 없습니다.", result.errors)

    def test_should_reject_section_without_bullet(self):
        body = GOOD_BODY.replace("- 배경", "배경")
        self.assertFalse(validate_pr("feat: x 추가", body).ok)

    def test_should_reject_title_over_80_chars(self):
        self.assertFalse(validate_pr("feat: " + "a" * 80, GOOD_BODY).ok)

    def test_fix_should_fill_missing_sections(self):
        fixed, fixes = fix_pr_body("## Why\n배경 설명")
        self.assertTrue(validate_pr("feat: x 추가", fixed).ok)
        self.assertEqual(len(fixes), 3)


class TitleHelpersTest(unittest.TestCase):
    def test_normalize_removes_quotes_period_and_emoji(self):
        self.assertEqual(normalize_title('"✨ feat: 기능 추가."\n둘째 줄'), "feat: 기능 추가")

    def test_truncate_cuts_on_word_boundary(self):
        title = truncate_title("feat: " + "word " * 30, 72)
        self.assertLessEqual(len(title), 72)
        self.assertFalse(title.endswith(" "))


if __name__ == "__main__":
    unittest.main()
