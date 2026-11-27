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


if __name__ == "__main__":
    unittest.main()
