import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from gitgen.ai_client import AIClient, AIClientError, AIParams, load_api_key


def fake_response(payload: dict):
    response = mock.MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    return response


class AIClientTest(unittest.TestCase):
    def setUp(self):
        self.client = AIClient("test-key", "https://example.invalid/v1", AIParams())

    def test_missing_api_key_raises_with_guide(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(AIClientError, "AI_API_KEY 환경변수"):
                load_api_key()

    def test_successful_call_parses_content_and_counts(self):
        payload = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        with mock.patch("urllib.request.urlopen", return_value=fake_response(payload)) as opened:
            result = self.client.chat([{"role": "user", "content": "hi"}])
        request = opened.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(body["temperature"], AIParams().temperature)
        self.assertEqual(result.completion_tokens, 5)
        self.assertEqual(self.client.call_count, 1)

    def test_401_maps_to_auth_failure(self):
        error = urllib.error.HTTPError("u", 401, "Unauthorized", {},
                                       io.BytesIO(b'{"error": {"message": "bad key"}}'))
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(AIClientError, "인증 실패.*\\n.*bad key"):
                self.client.chat([])

    def test_network_error_message(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no route")):
            with self.assertRaisesRegex(AIClientError, "네트워크 오류: no route"):
                self.client.chat([])

    def test_empty_content_raises(self):
        payload = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
        with mock.patch("urllib.request.urlopen", return_value=fake_response(payload)):
            with self.assertRaisesRegex(AIClientError, "빈 응답"):
                self.client.chat([])


if __name__ == "__main__":
    unittest.main()
