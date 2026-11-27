"""AI 응답(JSON)을 커밋/PR 초안 텍스트로 변환한다. JSON이 깨지면 일반 텍스트로 대체 파싱."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .validator import PR_SECTIONS, normalize_title

PR_JSON_KEYS = {"Why": "why", "What": "what", "How to Test": "how_to_test"}


@dataclass
class CommitDraft:
    title: str
    body: list[str]

    def render(self) -> str:
        if not self.body:
            return self.title
        bullets = "\n".join(f"- {_strip_bullet(item)}" for item in self.body)
        return f"{self.title}\n\n{bullets}"


@dataclass
class PrDraft:
    title: str
    body: str


def _strip_bullet(text: str) -> str:
    return re.sub(r"^\s*[-*]\s+", "", str(text)).strip()


JSON_STRING = r'"((?:[^"\\]|\\.)*)"'


def extract_json(text: str) -> dict | None:
    """응답에서 첫 번째 JSON 객체를 꺼낸다 (코드펜스로 감싸도 처리).

    max_tokens에 걸려 JSON이 중간에 잘린 경우, 완성된 값만 복구한다.
    """
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            return data
    return salvage_truncated_json(text) if "{" in text else None


def _decode(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw


def salvage_truncated_json(text: str) -> dict | None:
    """잘린 JSON에서 닫힌 문자열 값만 골라 dict로 재구성한다."""
    data: dict[str, object] = {}
    title = re.search(r'"title"\s*:\s*' + JSON_STRING, text)
    if title:
        data["title"] = _decode(title.group(1))
    for key in ("body", "why", "what", "how_to_test"):
        array = re.search(rf'"{key}"\s*:\s*\[([\s\S]*?)(?:\]|$)', text)
        if array:
            data[key] = [_decode(item) for item in re.findall(JSON_STRING, array.group(1))]
    return data or None


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_strip_bullet(item) for item in value if str(item).strip()]


def parse_commit(text: str) -> CommitDraft:
    data = extract_json(text)
    if data is not None:
        return CommitDraft(normalize_title(str(data.get("title", ""))), _as_list(data.get("body")))
    lines = [line for line in text.strip().splitlines() if not line.startswith("```")]
    title = normalize_title(lines[0]) if lines else ""
    return CommitDraft(title, [line for line in lines[1:] if line.strip()])


def render_pr_body(sections: dict[str, list[str]]) -> str:
    parts = []
    for name in PR_SECTIONS:
        bullets = "\n".join(f"- {item}" for item in sections.get(name, []))
        parts.append(f"## {name}\n{bullets}".rstrip())
    return "\n\n".join(parts)


def parse_pr(text: str) -> PrDraft:
    data = extract_json(text)
    if data is not None:
        sections = {name: _as_list(data.get(key)) for name, key in PR_JSON_KEYS.items()}
        return PrDraft(normalize_title(str(data.get("title", ""))), render_pr_body(sections))
    lines = text.strip().splitlines()
    title = normalize_title(lines[0]) if lines else ""
    return PrDraft(title, "\n".join(lines[1:]).strip())
