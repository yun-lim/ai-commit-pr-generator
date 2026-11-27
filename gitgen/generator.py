"""생성 → 검증 → (선택) 1회 재생성 → 후처리 흐름."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import output
from .ai_client import AIClient, ChatResult
from .drafts import CommitDraft, PrDraft, parse_commit, parse_pr
from .prompts import build_retry_message
from .validator import (
    COMMIT_TITLE_MAX,
    PR_TITLE_MAX,
    ValidationResult,
    fix_pr_body,
    truncate_title,
    validate_commit,
    validate_pr,
)


@dataclass
class Outcome:
    draft: CommitDraft | PrDraft
    validation: ValidationResult
    fixes: list[str] = field(default_factory=list)


def _call(client: AIClient, messages: list[dict[str, str]]) -> ChatResult:
    output.info(f"AI API 요청 중... (model={client.params.model}, "
                f"temperature={client.params.temperature}, max_tokens={client.params.max_tokens})")
    result = client.chat(messages)
    output.info(f"응답 수신: prompt {result.prompt_tokens} / completion {result.completion_tokens} tokens")
    if result.finish_reason == "length":
        output.warn("max_tokens에 도달해 응답이 잘렸을 수 있습니다. --max-tokens를 늘려 보세요.")
    return result


def _generate(client, messages, parse, validate, retry):
    result = _call(client, messages)
    draft = parse(result.content)
    validation = validate(draft)
    if not validation.ok and retry:
        output.warn("형식 검증 실패 → 위반 사항을 알려주고 1회 재생성합니다: " + "; ".join(validation.errors))
        result = _call(client, messages + build_retry_message(result.content, validation.errors))
        draft = parse(result.content)
        validation = validate(draft)
    return draft, validation


def generate_commit(client: AIClient, messages: list[dict[str, str]], retry: bool) -> Outcome:
    draft, validation = _generate(
        client, messages, parse_commit, lambda d: validate_commit(d.render()), retry)
    fixes = []
    if len(draft.title) > COMMIT_TITLE_MAX:
        draft.title = truncate_title(draft.title, COMMIT_TITLE_MAX)
        fixes.append(f"커밋 제목을 {COMMIT_TITLE_MAX}자 이내로 자름")
    if fixes:
        validation = validate_commit(draft.render())
    return Outcome(draft, validation, fixes)


def generate_pr(client: AIClient, messages: list[dict[str, str]], retry: bool) -> Outcome:
    draft, validation = _generate(
        client, messages, parse_pr, lambda d: validate_pr(d.title, d.body), retry)
    fixes = []
    if len(draft.title) > PR_TITLE_MAX:
        draft.title = truncate_title(draft.title, PR_TITLE_MAX)
        fixes.append(f"PR 제목을 {PR_TITLE_MAX}자 이내로 자름")
    if not validation.ok:
        draft.body, body_fixes = fix_pr_body(draft.body)
        fixes.extend(body_fixes)
    if fixes:
        validation = validate_pr(draft.title, draft.body)
    return Outcome(draft, validation, fixes)
