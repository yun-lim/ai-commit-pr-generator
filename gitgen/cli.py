"""CLI 진입점: `python main.py commit|pr [옵션]`."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import output
from .ai_client import (
    BASE_URL_ENV, DEFAULT_BASE_URL, DEFAULT_MAX_TOKENS, DEFAULT_MODEL, DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT, MODEL_ENV, AIClient, AIClientError, AIParams, load_api_key,
)
from .generator import Outcome, generate_commit, generate_pr
from .git_collector import GitChanges, GitError, collect_commit_changes, collect_pr_changes
from .prompts import build_commit_messages, build_pr_messages
from .safe_mode import (
    DEFAULT_MAX_DIFF_CHARS, DEFAULT_MAX_FILES, DEFAULT_MAX_LINES, DiffReport, prepare_diff,
)

EXIT_OK = 0
EXIT_ERROR = 1
MAX_TEMPERATURE = 2.0


def _temperature(value: str) -> float:
    number = float(value)
    if not 0.0 <= number <= MAX_TEMPERATURE:
        raise argparse.ArgumentTypeError(f"temperature는 0.0~{MAX_TEMPERATURE} 범위여야 합니다.")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("1 이상의 정수여야 합니다.")
    return number


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    ai = parser.add_argument_group("AI API 파라미터")
    ai.add_argument("-m", "--model", default=os.environ.get(MODEL_ENV, DEFAULT_MODEL),
                    help=f"모델 이름 (기본: ${MODEL_ENV} 또는 {DEFAULT_MODEL})")
    ai.add_argument("-t", "--temperature", type=_temperature, default=DEFAULT_TEMPERATURE,
                    help=f"창의성/무작위성 0.0~2.0 (기본: {DEFAULT_TEMPERATURE})")
    ai.add_argument("--max-tokens", type=_positive_int, default=DEFAULT_MAX_TOKENS,
                    help=f"응답 최대 토큰 수 (기본: {DEFAULT_MAX_TOKENS})")
    ai.add_argument("--timeout", type=_positive_int, default=DEFAULT_TIMEOUT,
                    help=f"요청 타임아웃 초 (기본: {DEFAULT_TIMEOUT})")
    ai.add_argument("--retry", action="store_true",
                    help="형식 검증 실패 시 1회 재생성 (최대 2회 호출)")
    ctx = parser.add_argument_group("컨텍스트/출력")
    ctx.add_argument("-c", "--context", help="변경 이유·요구사항 (프롬프트에 포함)")
    ctx.add_argument("--lang", choices=("ko", "en"), default="ko", help="작성 언어 (기본: ko)")
    ctx.add_argument("--save", type=Path, help="결과 저장 (commit: 메시지 전체, pr: 본문만)")
    ctx.add_argument("--dry-run", action="store_true", help="API를 호출하지 않고 프롬프트만 출력")
    safe = parser.add_argument_group("안전 모드 / 전송 제한")
    safe.add_argument("--safe-mode", action="store_true",
                      help="민감정보 마스킹 + 민감 파일 제외 + 파일/줄 수 제한")
    safe.add_argument("--max-files", type=_positive_int, default=DEFAULT_MAX_FILES,
                      help=f"safe-mode 최대 전송 파일 수 (기본: {DEFAULT_MAX_FILES})")
    safe.add_argument("--max-lines", type=_positive_int, default=DEFAULT_MAX_LINES,
                      help=f"safe-mode 최대 전송 줄 수 (기본: {DEFAULT_MAX_LINES})")
    safe.add_argument("--max-diff-chars", type=_positive_int, default=DEFAULT_MAX_DIFF_CHARS,
                      help=f"항상 적용되는 diff 최대 문자 수 (기본: {DEFAULT_MAX_DIFF_CHARS})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="git status/diff를 AI API로 요약해 커밋 메시지와 PR 초안을 만듭니다.")
    sub = parser.add_subparsers(dest="command", required=True)
    commit = sub.add_parser("commit", help="커밋 메시지 생성")
    _add_common_options(commit)
    pr = sub.add_parser("pr", help="PR 제목/본문 초안 생성")
    pr.add_argument("--base", default="main", help="비교 기준 브랜치 (기본: main)")
    _add_common_options(pr)
    return parser


def _collect(args: argparse.Namespace, cwd: Path) -> GitChanges:
    if args.command == "commit":
        changes = collect_commit_changes(cwd)
    else:
        changes = collect_pr_changes(cwd, args.base)
    output.info(f"현재 브랜치: {changes.branch}")
    output.info(f"Git status 수집 완료: {len(changes.files)}개 파일 변경 감지")
    output.info(f"Git diff 수집 완료: {changes.diff_line_count}줄 ({changes.diff_source})")
    return changes


def _prepare(args: argparse.Namespace, changes: GitChanges) -> tuple[str, DiffReport]:
    diff, report = prepare_diff(
        changes.diff, args.safe_mode, args.max_files, args.max_lines, args.max_diff_chars)
    if args.safe_mode:
        masked = ", ".join(f"{k} {v}건" for k, v in report.masked.items()) or "없음"
        output.info(f"safe-mode ON: 파일 {report.files_sent}/{report.files_total}개, "
                    f"줄 {report.lines_sent}/{report.lines_total}줄 전송, 마스킹 {masked}")
        if report.excluded_files:
            output.info(f"safe-mode: 민감 파일 제외 → {', '.join(report.excluded_files)}")
    if report.truncated_chars:
        output.warn(f"diff가 {args.max_diff_chars}자를 넘어 일부만 전송합니다.")
    return diff, report


def _print_outcome(args: argparse.Namespace, outcome: Outcome) -> str:
    for fix in outcome.fixes:
        output.info(f"후처리: {fix}")
    for warning in outcome.validation.warnings:
        output.warn(f"검토 권장: {warning}")
    for problem in outcome.validation.errors:
        output.warn(f"규칙 위반(직접 수정 필요): {problem}")
    if args.command == "commit":
        text = outcome.draft.render()
        output.done("커밋 메시지 생성 완료")
        output.print_section("Commit Message", text)
        return text
    output.done("PR 초안 생성 완료")
    output.print_section("PR Title", outcome.draft.title)
    output.print_section("PR Body", outcome.draft.body)
    return outcome.draft.body


def run(args: argparse.Namespace, cwd: Path) -> int:
    changes = _collect(args, cwd)
    if not changes.has_changes:
        target = "커밋 메시지" if args.command == "commit" else "PR 초안"
        output.info(f"변경 사항이 없습니다. {target}를 생성하지 않고 종료합니다.")
        return EXIT_OK
    diff, report = _prepare(args, changes)
    build = build_commit_messages if args.command == "commit" else build_pr_messages
    messages = build(changes, diff, args.context, args.lang, report, args.max_tokens)
    if args.dry_run:
        output.info("dry-run: API를 호출하지 않고 프롬프트만 출력합니다.")
        for message in messages:
            output.print_section(f"Prompt ({message['role']})", message["content"])
        return EXIT_OK
    params = AIParams(args.model, args.temperature, args.max_tokens, args.timeout)
    client = AIClient(load_api_key(), os.environ.get(BASE_URL_ENV, DEFAULT_BASE_URL), params)
    generate = generate_commit if args.command == "commit" else generate_pr
    try:
        outcome = generate(client, messages, args.retry)
    finally:
        output.info(f"AI API 호출 횟수: {client.call_count}회")
    text = _print_outcome(args, outcome)
    if args.save:
        args.save.write_text(text + "\n", encoding="utf-8")
        usage = (f"git commit -F {args.save}" if args.command == "commit"
                 else f'gh pr create --title "<PR Title>" --body-file {args.save}')
        output.info(f"저장 완료: {args.save} (예: {usage})")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args, Path.cwd())
    except (GitError, AIClientError) as err:
        output.error(str(err))
        return EXIT_ERROR
    except KeyboardInterrupt:
        output.error("사용자에 의해 중단되었습니다.")
        return EXIT_ERROR
