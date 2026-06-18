from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class WorkMessage:
    timestamp: datetime
    role: str
    text: str


@dataclass
class ThreadSummary:
    path: Path
    thread_id: str | None = None
    title: str = ""
    cwd: str = ""
    source: str = "filesystem"
    start: datetime | None = None
    end: datetime | None = None
    user_messages: int = 0
    assistant_messages: int = 0
    inherited_context_messages_dropped: int = 0
    user_preview: list[WorkMessage] = field(default_factory=list)


@dataclass
class GitCommit:
    hash: str
    date: str
    author: str
    subject: str


@dataclass
class GitRepoActivity:
    path: Path
    branch: str = ""
    status: str = ""
    commits: list[GitCommit] = field(default_factory=list)
    diff_stat: str = ""


@dataclass
class ReportContext:
    date: str
    workspace: Path
    hours: float
    token_total: int | None
    threads: list[ThreadSummary]
    git_repos: list[GitRepoActivity]
