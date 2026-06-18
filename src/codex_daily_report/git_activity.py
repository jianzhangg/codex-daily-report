from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

from .models import GitCommit, GitRepoActivity


def discover_git_repos(workspace: Path, max_depth: int = 2) -> list[Path]:
    workspace = workspace.expanduser().resolve()
    repos: list[Path] = []
    stack: list[tuple[Path, int]] = [(workspace, 0)]
    seen: set[Path] = set()

    while stack:
        path, depth = stack.pop()
        if path in seen:
            continue
        seen.add(path)

        if (path / ".git").exists():
            repos.append(path)
            continue

        if depth >= max_depth:
            continue
        try:
            children = [child for child in path.iterdir() if child.is_dir() and not child.name.startswith(".")]
        except OSError:
            continue
        for child in children:
            stack.append((child, depth + 1))

    return sorted(repos)


def run_git(repo: Path, args: list[str], timeout: int = 20) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    output = result.stdout.strip()
    if result.returncode != 0 and result.stderr.strip():
        return f"ERROR: {result.stderr.strip()}"
    return output


def parse_commits(raw: str) -> list[GitCommit]:
    commits: list[GitCommit] = []
    for line in raw.splitlines():
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        commits.append(GitCommit(hash=parts[0], date=parts[1], author=parts[2], subject=parts[3]))
    return commits


def collect_git_activity(
    workspace: Path,
    date_text: str,
    max_depth: int = 2,
    max_commits: int = 40,
) -> list[GitRepoActivity]:
    repos = discover_git_repos(workspace, max_depth=max_depth)
    activities: list[GitRepoActivity] = []
    for repo in repos:
        branch = run_git(repo, ["branch", "--show-current"])
        status = run_git(repo, ["status", "--short"])
        raw_commits = run_git(
            repo,
            [
                "log",
                "--all",
                f"--since={date_text} 00:00:00",
                f"--until={date_text} 23:59:59",
                "--date=local",
                "--pretty=format:%h%x09%ad%x09%an%x09%s",
                f"--max-count={max_commits}",
            ],
        )
        diff_stat = run_git(repo, ["diff", "--stat"])

        if not status and not raw_commits and not diff_stat:
            continue

        activities.append(
            GitRepoActivity(
                path=repo,
                branch=branch,
                status=status,
                commits=parse_commits(raw_commits),
                diff_stat=diff_stat,
            )
        )
    return activities


def today_text() -> str:
    return date.today().isoformat()
