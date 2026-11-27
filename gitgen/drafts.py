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


def extract_json(text: str) -> dict | None:
    """응답에서 첫 번째 JSON 객체를 꺼낸다 (코드펜스로 감싸도 처리)."""
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


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
