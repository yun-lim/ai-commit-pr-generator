"""OpenAI 호환 Chat Completions REST API 클라이언트 (표준 라이브러리 urllib만 사용)."""

from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass

API_KEY_ENV = "AI_API_KEY"
BASE_URL_ENV = "AI_API_BASE_URL"
MODEL_ENV = "AI_MODEL"
DEFAULT_BASE_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_MODEL = "openai/gpt-4.1-mini"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 700
DEFAULT_TIMEOUT = 30
ERROR_DETAIL_LIMIT = 200


def build_ssl_context() -> ssl.SSLContext:
    """certifi가 설치되어 있으면 그 CA 번들을, 없으면 시스템 기본 인증서를 사용한다."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


class AIClientError(Exception):
    """API 호출 실패. 메시지에 원인을 담는다."""


@dataclass
class AIParams:
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout: int = DEFAULT_TIMEOUT


@dataclass
class ChatResult:
    content: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int


def load_api_key() -> str:
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        raise AIClientError(
            f"{API_KEY_ENV} 환경변수가 설정되지 않았습니다.\n"
            f'  예) export {API_KEY_ENV}="YOUR_KEY"'
        )
    return api_key


class AIClient:
    def __init__(self, api_key: str, base_url: str, params: AIParams) -> None:
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.params = params
        self.call_count = 0

    def chat(self, messages: list[dict[str, str]]) -> ChatResult:
        """요청 구성 → 전송 → 응답 파싱. 실패 시 AIClientError."""
        request = self._build_request(messages)
        self.call_count += 1
        try:
            with urllib.request.urlopen(
                request, timeout=self.params.timeout, context=build_ssl_context()
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            raise AIClientError(describe_http_error(err.code, _read_error_detail(err))) from err
        except (socket.timeout, TimeoutError) as err:
            raise AIClientError(
                f"요청 시간 초과({self.params.timeout}초): 네트워크 상태를 확인하거나 --timeout을 늘리세요."
            ) from err
        except urllib.error.URLError as err:
            if isinstance(err.reason, ssl.SSLCertVerificationError):
                raise AIClientError(
                    "SSL 인증서 검증 실패: `pip install -r requirements.txt`(certifi 설치) 후 다시 실행하세요."
                ) from err
            raise AIClientError(f"네트워크 오류: {err.reason} (BASE_URL={self.base_url})") from err
        except json.JSONDecodeError as err:
            raise AIClientError("응답 파싱 실패: JSON 형식이 아닌 응답을 받았습니다.") from err
        return parse_chat_response(payload)

    def _build_request(self, messages: list[dict[str, str]]) -> urllib.request.Request:
        body = {
            "model": self.params.model,
            "messages": messages,
            "temperature": self.params.temperature,
            "max_tokens": self.params.max_tokens,
        }
        return urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )


def parse_chat_response(payload: dict) -> ChatResult:
    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as err:
        raise AIClientError(f"응답 구조가 예상과 다릅니다: {str(payload)[:ERROR_DETAIL_LIMIT]}") from err
    if not content.strip():
        raise AIClientError("AI가 빈 응답을 반환했습니다. --max-tokens를 늘리거나 다른 모델을 사용하세요.")
    usage = payload.get("usage") or {}
    return ChatResult(
        content=content,
        finish_reason=choice.get("finish_reason") or "",
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )


def _read_error_detail(err: urllib.error.HTTPError) -> str:
    try:
        raw = err.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    try:
        message = json.loads(raw).get("error", {}).get("message", raw)
    except (json.JSONDecodeError, AttributeError):
        message = raw
    return str(message)[:ERROR_DETAIL_LIMIT]


def describe_http_error(status: int, detail: str) -> str:
    """HTTP 상태 코드를 사용자가 바로 조치할 수 있는 메시지로 바꾼다."""
    if status in (401, 403):
        reason = f"인증 실패(HTTP {status}): {API_KEY_ENV} 값이 올바른지, 권한이 있는지 확인하세요."
    elif status == 404:
        reason = f"리소스 없음(HTTP 404): --model 이름 또는 {BASE_URL_ENV}를 확인하세요."
    elif status == 429:
        reason = "요청 한도 초과(HTTP 429): 잠시 후 다시 시도하거나 사용량/요금제를 확인하세요."
    elif status == 400:
        reason = "잘못된 요청(HTTP 400): 모델·temperature·max_tokens 값을 확인하세요."
    elif status >= 500:
        reason = f"AI 서버 오류(HTTP {status}): 잠시 후 다시 시도하세요."
    else:
        reason = f"API 호출 실패(HTTP {status})"
    return f"{reason}\n  서버 메시지: {detail}" if detail else reason
