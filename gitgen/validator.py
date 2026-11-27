"""생성된 커밋/PR 텍스트의 길이·템플릿·표현 규칙 검증과 후처리."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

COMMIT_TITLE_RECOMMENDED = 50
COMMIT_TITLE_MAX = 72
PR_TITLE_MAX = 80
COMMIT_BODY_MAX_BULLETS = 3
PR_SECTIONS = ("Why", "What", "How to Test")
PLACEHOLDER_BULLET = "- (작성 필요: AI 초안에 내용이 없어 직접 보완하세요)"

CONVENTIONAL_TITLE = re.compile(
    r"^(feat|fix|docs|style|refactor|test|chore|perf|ci|build|revert)(\([\w\-./ ]+\))?!?: \S"
)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
VAGUE_TITLES = re.compile(r"(?i)^(\w+(\([^)]*\))?: )?(update|fix|change|수정|변경|업데이트)( files?| code| 코드| 파일)?$")
BULLET = re.compile(r"^\s*[-*] \S")


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def normalize_title(title: str) -> str:
    """안전한 후처리: 첫 줄만, 따옴표/마크다운 헤더/이모지/끝 마침표 제거."""
    first_line = title.strip().splitlines()[0] if title.strip() else ""
    cleaned = EMOJI.sub("", first_line).strip().strip("`\"'").lstrip("# ").strip()
    return cleaned.rstrip(". ").strip()


def truncate_title(title: str, limit: int) -> str:
    """길이 초과 시 단어 경계에서 자른다."""
    if len(title) <= limit:
        return title
    cut = title[:limit].rstrip()
    space = cut.rfind(" ")
    return cut[:space].rstrip(" ,") if space > limit * 0.6 else cut


def _check_title(title: str, limit: int, label: str, result: ValidationResult) -> None:
    if not title:
        result.errors.append(f"{label}이 비어 있습니다.")
        return
    if len(title) > limit:
        result.errors.append(f"{label}이 {len(title)}자입니다 (최대 {limit}자).")
    if not CONVENTIONAL_TITLE.match(title):
        result.warnings.append(f"{label}이 `type(scope): 요약` 형식이 아닙니다.")
    if VAGUE_TITLES.match(title):
        result.errors.append(f"{label}이 모호합니다('{title}'). 무엇을 바꿨는지 구체적으로 쓰세요.")


def validate_commit(message: str) -> ValidationResult:
    result = ValidationResult()
    lines = message.strip().splitlines()
    title = lines[0].strip() if lines else ""
    _check_title(title, COMMIT_TITLE_MAX, "커밋 제목", result)
    if title and COMMIT_TITLE_RECOMMENDED < len(title) <= COMMIT_TITLE_MAX:
        result.warnings.append(f"커밋 제목이 {len(title)}자입니다 ({COMMIT_TITLE_RECOMMENDED}자 이내 권장).")
    if title.endswith("."):
        result.errors.append("커밋 제목 끝에 마침표가 있습니다.")
    body = lines[1:]
    if body and body[0].strip():
        result.errors.append("커밋 제목과 본문 사이에 빈 줄이 필요합니다.")
    body_text = [line for line in body if line.strip()]
    bullet_count = sum(1 for line in body_text if BULLET.match(line))
    if body_text and not bullet_count:
        result.errors.append("커밋 본문에 핵심 변경 사항 불릿(- ...)이 없습니다.")
    if bullet_count > COMMIT_BODY_MAX_BULLETS:
        result.warnings.append(
            f"커밋 본문 불릿이 {bullet_count}개입니다 ({COMMIT_BODY_MAX_BULLETS}개 이하 권장).")
    return result


def split_sections(body: str) -> dict[str, list[str]]:
    """`## 헤더` 기준으로 섹션별 줄 목록을 만든다."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        header = re.match(r"^##\s+(.+?)\s*$", line)
        if header:
            current = header.group(1)
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def validate_pr(title: str, body: str) -> ValidationResult:
    result = ValidationResult()
    if "\n" in title.strip():
        result.errors.append("PR 제목은 1줄이어야 합니다.")
    _check_title(title.strip(), PR_TITLE_MAX, "PR 제목", result)
    sections = split_sections(body)
    for name in PR_SECTIONS:
        if name not in sections:
            result.errors.append(f"PR 본문에 '## {name}' 섹션이 없습니다.")
        elif not any(BULLET.match(line) for line in sections[name]):
            result.errors.append(f"'## {name}' 섹션에 불릿이 1개 이상 필요합니다.")
    return result


def fix_pr_body(body: str) -> tuple[str, list[str]]:
    """필수 섹션/불릿이 빠졌을 때 자리표시 불릿으로 채워 템플릿을 보장한다."""
    sections = split_sections(body)
    fixes: list[str] = []
    parts = []
    for name in PR_SECTIONS:
        lines = [line for line in sections.get(name, []) if line.strip()]
        if not any(BULLET.match(line) for line in lines):
            lines = [f"- {line.strip()}" for line in lines] or [PLACEHOLDER_BULLET]
            fixes.append(f"'## {name}' 섹션 불릿 보정")
        parts.append(f"## {name}\n" + "\n".join(lines))
    return "\n\n".join(parts), fixes
