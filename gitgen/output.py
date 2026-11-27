"""터미널 출력: 진행 로그는 stderr, 결과물은 stdout(구분선으로 구획)."""

from __future__ import annotations

import sys

SECTION_WIDTH = 50


def log(level: str, message: str) -> None:
    print(f"[{level}] {message}", file=sys.stderr)


def info(message: str) -> None:
    log("INFO", message)


def warn(message: str) -> None:
    log("WARN", message)


def error(message: str) -> None:
    log("ERROR", message)


def done(message: str) -> None:
    log("DONE", message)


def print_section(title: str, content: str) -> None:
    print(f"\n--- {title} ---")
    print(content.rstrip())
    print("-" * SECTION_WIDTH)
