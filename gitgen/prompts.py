"""프롬프트 설계: 역할(system) + 규칙/양식 + 변경 맥락(status, diff, 사용자 context)."""

from __future__ import annotations

from .git_collector import GitChanges
from .validator import COMMIT_TITLE_MAX, COMMIT_TITLE_RECOMMENDED, PR_TITLE_MAX

COMMIT_TYPES = "feat, fix, docs, style, refactor, test, chore, perf, ci, build"
LANGUAGE_NAMES = {"ko": "한국어", "en": "English"}

SYSTEM_PROMPT = (
    "당신은 코드 리뷰 경험이 많은 시니어 소프트웨어 엔지니어입니다. "
    "주어진 git status / git diff만 근거로 변경 사항을 정확하게 요약합니다. "
    "diff에 없는 기능·이유·테스트 결과를 지어내지 않습니다. "
    "[MASKED_...] 로 표시된 값은 민감정보이므로 추측하거나 복원하지 않습니다. "
    "반드시 요청된 JSON 객체 하나만 출력하고, 코드펜스나 설명 문장을 덧붙이지 않습니다."
)

COMMIT_RULES = f"""\
[커밋 메시지 규칙]
1. 제목(title): Conventional Commits 형식 `<type>(<scope>): <요약>` (scope는 생략 가능)
   - type은 다음 중 하나: {COMMIT_TYPES}
   - {COMMIT_TITLE_RECOMMENDED}자 이내 권장, 절대 {COMMIT_TITLE_MAX}자를 넘기지 않음
   - 한 줄, 끝에 마침표 없음, 이모지 없음, "이 커밋은" 같은 군더더기 없음
   - "update files", "코드 수정" 처럼 모호한 표현 금지 → 무엇을 왜 바꿨는지 드러낼 것
2. 본문(body): 핵심 변경 사항 1~3개를 불릿 문자열 배열로 작성
   - 각 불릿에 변경된 파일 또는 모듈 이름을 1개 이상 언급 (예: "git_collector.py: ...")
   - 한 불릿은 한 문장, 72자 안팎

[출력 JSON 스키마]
{{"title": "feat(cli): ...", "body": ["파일명: 변경 내용", "..."]}}
"""

PR_RULES = f"""\
[PR 규칙]
1. 제목(title): 한 줄, 최대 {PR_TITLE_MAX}자, Conventional Commits 형식 `<type>(<scope>): <요약>`
2. 본문은 세 섹션으로 구성하며 각 섹션은 1~4개의 불릿 문자열 배열
   - why: 변경 배경/문제 상황 (diff와 사용자 맥락에서 추론 가능한 범위만)
   - what: 핵심 변경 사항, 파일/모듈 이름 포함
   - how_to_test: 리뷰어가 그대로 따라 할 수 있는 확인 절차 (실행 명령은 백틱으로 감싸기)
3. 불릿 문자열 앞에 "-" 기호를 붙이지 않음 (프로그램이 붙임)

[출력 JSON 스키마]
{{"title": "feat(cli): ...", "why": ["..."], "what": ["..."], "how_to_test": ["..."]}}
"""


def _format_files(changes: GitChanges) -> str:
    if not changes.files:
        return "(파일 목록 없음)"
    return "\n".join(f"- [{f.label}] {f.path}" for f in changes.files)


def _context_block(changes: GitChanges, diff: str, user_context: str | None, lang: str) -> str:
    context_text = user_context.strip() if user_context else "(제공되지 않음 — diff만으로 판단)"
    return (
        f"[작성 언어] {LANGUAGE_NAMES.get(lang, lang)} (type/scope 키워드와 코드 식별자는 영어 유지)\n\n"
        f"[현재 브랜치] {changes.branch}\n"
        f"[diff 기준] {changes.diff_source}\n\n"
        f"[변경 이유/요구사항 — 사용자 제공]\n{context_text}\n\n"
        f"[git status: 변경 파일 {len(changes.files)}개]\n{_format_files(changes)}\n\n"
        f"[git diff]\n```diff\n{diff}\n```"
    )


def build_commit_messages(
    changes: GitChanges, diff: str, user_context: str | None = None, lang: str = "ko"
) -> list[dict[str, str]]:
    user = f"{COMMIT_RULES}\n{_context_block(changes, diff, user_context, lang)}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def build_pr_messages(
    changes: GitChanges, diff: str, user_context: str | None = None, lang: str = "ko"
) -> list[dict[str, str]]:
    user = f"{PR_RULES}\n{_context_block(changes, diff, user_context, lang)}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def build_retry_message(previous: str, errors: list[str]) -> list[dict[str, str]]:
    """검증 실패 시 1회 재생성용 후속 메시지 (이전 답변 + 위반 사항)."""
    feedback = "\n".join(f"- {error}" for error in errors)
    return [
        {"role": "assistant", "content": previous},
        {
            "role": "user",
            "content": f"위 결과가 다음 규칙을 위반했습니다. 규칙을 지켜 같은 JSON 스키마로 다시 출력하세요.\n{feedback}",
        },
    ]
