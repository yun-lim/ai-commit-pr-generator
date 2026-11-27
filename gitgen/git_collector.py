"""Git 변경 사항 수집: git status / git diff 결과를 프로그램 입력으로 변환한다."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

STATUS_LABELS = {
    "M": "수정",
    "A": "추가",
    "D": "삭제",
    "R": "이름변경",
    "C": "복사",
    "U": "충돌",
    "?": "신규(untracked)",
}


class GitError(Exception):
    """Git 명령 실행 실패 또는 실행 위치 오류."""


@dataclass
class FileStatus:
    code: str
    path: str

    @property
    def label(self) -> str:
        key = self.code.strip()[:1] or "M"
        return STATUS_LABELS.get(key, self.code.strip())


@dataclass
class GitChanges:
    branch: str
    files: list[FileStatus] = field(default_factory=list)
    diff: str = ""
    diff_source: str = ""

    @property
    def has_changes(self) -> bool:
        return bool(self.diff.strip())

    @property
    def diff_line_count(self) -> int:
        return len(self.diff.splitlines())


def run_git(args: list[str], cwd: Path, allowed_codes: tuple[int, ...] = (0,)) -> str:
    """git 명령을 실행하고 stdout을 반환한다."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as err:
        raise GitError("git 명령을 찾을 수 없습니다. Git이 설치되어 있는지 확인하세요.") from err
    if result.returncode not in allowed_codes:
        raise GitError(f"git {' '.join(args)} 실패: {result.stderr.strip()}")
    return result.stdout


def ensure_repo_root(cwd: Path) -> None:
    """Git이 초기화된 프로젝트 루트에서 실행 중인지 확인한다."""
    try:
        top_level = run_git(["rev-parse", "--show-toplevel"], cwd).strip()
    except GitError as err:
        raise GitError(
            "Git 저장소가 아닙니다. git init 된 프로젝트 루트 디렉토리에서 실행하세요."
        ) from err
    if Path(top_level).resolve() != cwd.resolve():
        raise GitError(f"프로젝트 루트 디렉토리에서 실행하세요: cd {top_level}")


def parse_status(output: str) -> tuple[str, list[FileStatus]]:
    """`git status --porcelain=v1 --branch` 출력에서 브랜치와 파일 목록을 파싱한다."""
    branch = "(unknown)"
    files: list[FileStatus] = []
    for line in output.splitlines():
        if line.startswith("## "):
            branch = _parse_branch(line[3:])
            continue
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(FileStatus(code=code, path=path.strip('"')))
    return branch, files


def _parse_branch(header: str) -> str:
    for prefix in ("No commits yet on ", "Initial commit on "):
        if header.startswith(prefix):
            return header[len(prefix):].strip()
    return header.split("...", 1)[0].strip()


def collect_status(cwd: Path) -> tuple[str, list[FileStatus]]:
    output = run_git(["status", "--porcelain=v1", "--branch", "--untracked-files=all"], cwd)
    return parse_status(output)


def collect_untracked_diff(cwd: Path, files: list[FileStatus]) -> str:
    """untracked 파일은 git diff에 안 잡히므로 /dev/null 대비 diff로 내용을 만든다."""
    chunks = []
    for item in files:
        if item.code == "??":
            # --no-index 비교는 차이가 있으면 종료 코드 1을 반환한다.
            chunks.append(
                run_git(["diff", "--no-index", "--", "/dev/null", item.path], cwd, (0, 1))
            )
    return "".join(chunks)


def collect_commit_changes(cwd: Path) -> GitChanges:
    """커밋용 변경 사항: staged가 있으면 staged만, 없으면 작업 트리 전체."""
    ensure_repo_root(cwd)
    branch, files = collect_status(cwd)
    staged = run_git(["diff", "--cached"], cwd)
    if staged.strip():
        staged_files = [f for f in files if f.code[0] not in (" ", "?")]
        return GitChanges(branch, staged_files, staged, "staged (git diff --cached)")
    working = run_git(["diff"], cwd) + collect_untracked_diff(cwd, files)
    return GitChanges(branch, files, working, "working tree (git diff + untracked)")


def collect_pr_changes(cwd: Path, base: str) -> GitChanges:
    """PR용 변경 사항: base...HEAD diff, 없으면 커밋 전 작업 트리 변경으로 대체."""
    ensure_repo_root(cwd)
    branch, files = collect_status(cwd)
    try:
        branch_diff = run_git(["diff", f"{base}...HEAD"], cwd)
    except GitError:
        branch_diff = ""
    if branch != base and branch_diff.strip():
        names = run_git(["diff", "--name-status", f"{base}...HEAD"], cwd)
        return GitChanges(branch, _parse_name_status(names), branch_diff, f"git diff {base}...HEAD")
    fallback = collect_commit_changes(cwd)
    fallback.diff_source += f" — '{base}' 대비 커밋된 차이가 없어 작업 트리 기준"
    return fallback


def _parse_name_status(output: str) -> list[FileStatus]:
    files = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            files.append(FileStatus(code=parts[0][:1] + " ", path=parts[-1]))
    return files
