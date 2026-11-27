"""프롬프트 설계: 역할(system) + 규칙/양식 + 변경 맥락(status, diff, 사용자 context)."""

from __future__ import annotations

from .git_collector import GitChanges
from .safe_mode import DiffReport
from .validator import COMMIT_TITLE_MAX, COMMIT_TITLE_RECOMMENDED, PR_TITLE_MAX

COMMIT_TYPES = "feat, fix, docs, style, refactor, test, chore, perf, ci, build"
LANGUAGE_NAMES = {"ko": "한국어", "en": "English"}
# max_tokens 구간별 작성 분량. 응답이 잘리지 않도록 예산 안에서 분량을 조절하게 한다.
BRIEF_TOKEN_LIMIT = 200
NORMAL_TOKEN_LIMIT = 450
DETAIL_GUIDES = {
    "간결": "커밋 본문 불릿 1개, PR 섹션당 불릿 1개, 각 불릿 40자 이내. 핵심만 쓸 것",
    "보통": "커밋 본문 불릿 2개, PR 섹션당 불릿 1~2개, 각 불릿 한 문장",
    "상세": "커밋 본문 불릿 3개, PR 섹션당 불릿 2~4개, 파일·함수 이름과 동작을 구체적으로",
}

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
2. 본문(body): 핵심 변경 사항을 불릿 문자열 배열로 최소 1개, 최대 3개 작성
   - 각 불릿에 변경된 파일 또는 모듈 이름을 1개 이상 언급 (예: "git_collector.py: ...")
   - 파일이 4개 이상이면 역할이 비슷한 파일을 한 불릿에 묶어 3개를 넘기지 않음
   - 한 불릿은 한 문장, 72자 안팎
   - diff 내용이 생략된 파일은 이름만으로 기능을 추측하지 말고, 확인된 내용만 쓸 것

[출력 JSON 스키마]
{{"title": "feat(cli): ...", "body": ["파일명: 변경 내용", "..."]}}
"""

PR_RULES = f"""\
[PR 규칙]
1. 제목(title): 한 줄, 최대 {PR_TITLE_MAX}자, Conventional Commits 형식 `<type>(<scope>): <요약>`
2. 본문은 세 섹션으로 구성하며 각 섹션은 1~4개의 불릿 문자열 배열
   - diff 내용이 생략된 파일은 이름만으로 기능을 추측하지 말 것
   - why: 변경 배경/문제 상황 (diff와 사용자 맥락에서 추론 가능한 범위만)
   - what: 핵심 변경 사항, 파일/모듈 이름 포함
   - how_to_test: 리뷰어가 그대로 따라 할 수 있는 확인 절차 (실행 명령은 백틱으로 감싸기)
     테스트 명령은 diff나 사용자 맥락에서 확인된 것만 쓰고, 확인되지 않으면 "테스트 명령 확인 필요"라고 쓸 것
3. 불릿 문자열 앞에 "-" 기호를 붙이지 않음 (프로그램이 붙임)

[출력 JSON 스키마]
{{"title": "feat(cli): ...", "why": ["..."], "what": ["..."], "how_to_test": ["..."]}}
"""


def _format_files(changes: GitChanges) -> str:
    if not changes.files:
        return "(파일 목록 없음)"
    return "\n".join(f"- [{f.label}] {f.path}" for f in changes.files)


def describe_scope(report: DiffReport | None) -> str:
    """AI가 '본 것'과 '못 본 것'을 구분하도록 diff 전송 범위를 알려준다."""
    if report is None:
        return "전체 diff"
    scope = f"파일 {report.files_sent}/{report.files_total}개, 줄 {report.lines_sent}/{report.lines_total}줄"
    partial = report.files_sent < report.files_total or report.lines_sent < report.lines_total
    if partial or report.truncated_chars:
        scope += " — 일부만 전송됨. 생략된 부분은 추측하지 말 것"
    return scope


def detail_level(max_tokens: int | None) -> str:
    if max_tokens is None or max_tokens > NORMAL_TOKEN_LIMIT:
        return "상세"
    return "간결" if max_tokens <= BRIEF_TOKEN_LIMIT else "보통"


def describe_budget(max_tokens: int | None) -> str:
    level = detail_level(max_tokens)
    budget = f"응답 최대 {max_tokens} 토큰 — " if max_tokens else ""
    return f"[작성 분량] {level}: {budget}{DETAIL_GUIDES[level]}. JSON이 잘리지 않게 예산 안에서 끝낼 것"


def _context_block(
    changes: GitChanges, diff: str, user_context: str | None, lang: str, report: DiffReport | None
) -> str:
    context_text = user_context.strip() if user_context else "(제공되지 않음 — diff만으로 판단)"
    return (
        f"[작성 언어] {LANGUAGE_NAMES.get(lang, lang)} (type/scope 키워드와 코드 식별자는 영어 유지)\n\n"
        f"[현재 브랜치] {changes.branch}\n"
        f"[diff 기준] {changes.diff_source}\n"
        f"[diff 전송 범위] {describe_scope(report)}\n\n"
        f"[변경 이유/요구사항 — 사용자 제공]\n{context_text}\n\n"
        f"[git status: 변경 파일 {len(changes.files)}개]\n{_format_files(changes)}\n\n"
        f"[git diff]\n```diff\n{diff}\n```"
    )


def build_commit_messages(
    changes: GitChanges,
    diff: str,
    user_context: str | None = None,
    lang: str = "ko",
    report: DiffReport | None = None,
    max_tokens: int | None = None,
) -> list[dict[str, str]]:
    user = (f"{COMMIT_RULES}\n{describe_budget(max_tokens)}\n\n"
            f"{_context_block(changes, diff, user_context, lang, report)}")
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def build_pr_messages(
    changes: GitChanges,
    diff: str,
    user_context: str | None = None,
    lang: str = "ko",
    report: DiffReport | None = None,
    max_tokens: int | None = None,
) -> list[dict[str, str]]:
    user = (f"{PR_RULES}\n{describe_budget(max_tokens)}\n\n"
            f"{_context_block(changes, diff, user_context, lang, report)}")
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
