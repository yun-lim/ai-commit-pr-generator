"""diff를 AI에 보내기 전 민감정보 마스킹(A)과 전송량 제한(B)을 적용한다."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

DEFAULT_MAX_FILES = 10
DEFAULT_MAX_LINES = 200
DEFAULT_MAX_DIFF_CHARS = 12_000

SENSITIVE_FILE_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "id_rsa*", "*credentials*", "*secret*",
)

# (라벨, 패턴). 순서가 중요하다: 구체적인 패턴을 먼저 적용한다.
MASK_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PRIVATE_KEY", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("API_KEY", re.compile(
        r"\b(?:sk-[A-Za-z0-9_\-]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}"
        r"|AIza[0-9A-Za-z_\-]{35}|xox[baprs]-[A-Za-z0-9\-]{10,}|vck_[A-Za-z0-9]{20,})")),
    ("TOKEN", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b")),
)
# KEY = "value" 형태의 할당은 변수명은 남기고 값만 가린다.
SECRET_ASSIGN = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:api[_-]?key|secret|token|passw(?:or)?d)[A-Z0-9_]*\s*[:=]\s*)"
    r"(['\"])([^'\"\s]{6,})\2"
)


@dataclass
class DiffReport:
    files_total: int = 0
    files_sent: int = 0
    lines_total: int = 0
    lines_sent: int = 0
    masked: dict[str, int] = field(default_factory=dict)
    excluded_files: list[str] = field(default_factory=list)
    truncated_chars: bool = False

    @property
    def masked_total(self) -> int:
        return sum(self.masked.values())


def split_diff_by_file(diff: str) -> list[str]:
    """`diff --git` 헤더 기준으로 파일 단위 청크로 나눈다."""
    chunks = re.split(r"(?m)^(?=diff --git )", diff)
    return [chunk for chunk in chunks if chunk.strip()]


def chunk_path(chunk: str) -> str:
    match = re.match(r"diff --git a/(\S+) b/(\S+)", chunk)
    return match.group(2) if match else ""


def is_sensitive_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pattern) for pattern in SENSITIVE_FILE_PATTERNS)


def mask_text(text: str, report: DiffReport) -> str:
    for label, pattern in MASK_RULES:
        text, count = pattern.subn(f"[MASKED_{label}]", text)
        if count:
            report.masked[label] = report.masked.get(label, 0) + count
    text, count = SECRET_ASSIGN.subn(lambda m: f"{m.group(1)}{m.group(2)}[MASKED_SECRET]{m.group(2)}", text)
    if count:
        report.masked["SECRET"] = report.masked.get("SECRET", 0) + count
    return text


def limit_chunks(chunks: list[str], max_files: int, max_lines: int, report: DiffReport) -> list[str]:
    """최대 파일 수/줄 수를 넘는 부분을 잘라낸다.

    줄 예산을 파일 수로 균등 배분해, 앞쪽 큰 파일이 예산을 독점하지 않게 한다.
    """
    selected = chunks[:max_files]
    if not selected:
        return []
    per_file = max(max_lines // len(selected), 1)
    kept: list[str] = []
    for chunk in selected:
        lines = chunk.splitlines(keepends=True)
        if len(lines) > per_file:
            lines = lines[:per_file] + ["... (safe-mode: 줄 수 제한으로 이후 생략)\n"]
            report.lines_sent += per_file
        else:
            report.lines_sent += len(lines)
        kept.append("".join(lines))
    return kept


def prepare_diff(
    diff: str,
    safe_mode: bool,
    max_files: int = DEFAULT_MAX_FILES,
    max_lines: int = DEFAULT_MAX_LINES,
    max_chars: int = DEFAULT_MAX_DIFF_CHARS,
) -> tuple[str, DiffReport]:
    """AI에 보낼 diff를 만든다. 문자 수 제한은 비용 보호를 위해 항상 적용한다."""
    chunks = split_diff_by_file(diff)
    report = DiffReport(files_total=len(chunks), lines_total=len(diff.splitlines()))
    if safe_mode:
        report.excluded_files = [chunk_path(c) for c in chunks if is_sensitive_file(chunk_path(c))]
        chunks = [c for c in chunks if not is_sensitive_file(chunk_path(c))]
        chunks = [mask_text(c, report) for c in chunks]
        chunks = limit_chunks(chunks, max_files, max_lines, report)
    else:
        report.lines_sent = report.lines_total
    report.files_sent = len(chunks)
    text = "".join(chunks)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (비용 보호: 최대 문자 수 제한으로 이후 생략)\n"
        report.truncated_chars = True
    return text, report
