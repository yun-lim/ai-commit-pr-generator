import unittest

from gitgen.drafts import parse_commit, parse_pr
from gitgen.validator import validate_commit, validate_pr


class ParseTest(unittest.TestCase):
    def test_parse_commit_json_inside_code_fence(self):
        draft = parse_commit('```json\n{"title": "feat(cli): commit 명령 추가.", "body": ["- cli.py: 추가"]}\n```')
        self.assertEqual(draft.title, "feat(cli): commit 명령 추가")
        self.assertEqual(draft.render(), "feat(cli): commit 명령 추가\n\n- cli.py: 추가")
        self.assertTrue(validate_commit(draft.render()).ok)

    def test_parse_commit_plain_text_fallback(self):
        draft = parse_commit("fix: 오류 메시지 개선\n- ai_client.py: 401 처리")
        self.assertEqual(draft.title, "fix: 오류 메시지 개선")

    def test_parse_pr_json_renders_template(self):
        draft = parse_pr('{"title": "feat: PR 생성", "why": ["배경"], "what": ["변경"], "how_to_test": ["실행"]}')
        self.assertIn("## How to Test\n- 실행", draft.body)
        self.assertTrue(validate_pr(draft.title, draft.body).ok)

    def test_truncated_json_keeps_completed_values(self):
        truncated = '{"title": "fix(cli): 오류 처리 개선", "why": ["키 누락 안내"], "what": ["cli.py: 종료 코드'
        draft = parse_pr(truncated)
        self.assertEqual(draft.title, "fix(cli): 오류 처리 개선")
        self.assertIn("## Why\n- 키 누락 안내", draft.body)
        self.assertNotIn("{", draft.title)


class BudgetPromptTest(unittest.TestCase):
    def test_detail_level_follows_max_tokens(self):
        from gitgen.prompts import detail_level
        self.assertEqual(detail_level(150), "간결")
        self.assertEqual(detail_level(300), "보통")
        self.assertEqual(detail_level(700), "상세")


if __name__ == "__main__":
    unittest.main()
