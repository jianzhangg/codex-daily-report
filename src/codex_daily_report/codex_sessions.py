from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import ThreadSummary, WorkMessage

NOISE_PREFIXES = (
    "# AGENTS.md instructions",
    "<environment_context>",
    "<permissions instructions>",
    "<app-context>",
    "<collaboration_mode>",
    "<personality_spec>",
    "<skills_instructions>",
    "<plugins_instructions>",
    "Another language model started to solve this problem",
)

REPORT_THREAD_KEYWORDS = (
    "生成今天的日报",
    "生成日报",
    "写日报",
    "daily report",
    "codex-daily-report",
)


def resolve_timezone(name: str) -> tzinfo:
    if name == "local":
        return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")
    return ZoneInfo(name)


def parse_timestamp(value: str | None, timezone: tzinfo) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone)
    except ValueError:
        return None


def normalize_text(text: str | None) -> str:
    return " ".join((text or "").split())


def is_context_noise(text: str | None) -> bool:
    stripped = (text or "").lstrip()
    return not stripped or any(stripped.startswith(prefix) for prefix in NOISE_PREFIXES)


def text_from_response_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(str(item.get("text") or item.get("output_text") or ""))
    return "".join(parts)


def in_workspace(cwd: str | None, workspace: Path) -> bool:
    if not cwd:
        return False
    try:
        cwd_path = Path(cwd).expanduser().resolve()
        workspace_path = workspace.expanduser().resolve()
    except OSError:
        return False
    return cwd_path == workspace_path or workspace_path in cwd_path.parents


def is_report_thread(title: str, user_texts: list[str]) -> bool:
    haystack = " ".join([title or "", *user_texts[:3]]).lower()
    return any(keyword.lower() in haystack for keyword in REPORT_THREAD_KEYWORDS)


def date_window(date_text: str, timezone: tzinfo) -> tuple[datetime, datetime]:
    start = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone)
    return start, start + timedelta(days=1)


def candidate_paths_from_state(
    codex_home: Path,
    date_text: str,
    workspace: Path,
) -> dict[Path, dict[str, str | None]]:
    state_db = codex_home / "state_5.sqlite"
    if not state_db.exists():
        return {}

    candidates: dict[Path, dict[str, str | None]] = {}
    try:
        con = sqlite3.connect(state_db)
    except sqlite3.Error:
        return candidates

    try:
        rows = con.execute(
            """
            select id, title, cwd, rollout_path, datetime(updated_at,'unixepoch','localtime')
            from threads
            where date(updated_at,'unixepoch','localtime')=?
            order by updated_at
            """,
            (date_text,),
        )
        for thread_id, title, cwd, rollout_path, updated_local in rows:
            if rollout_path and in_workspace(cwd, workspace):
                candidates[Path(rollout_path)] = {
                    "thread_id": thread_id,
                    "title": title or "",
                    "state_cwd": cwd or "",
                    "updated_local": updated_local or "",
                    "source": "state",
                }
    except sqlite3.Error:
        return candidates
    finally:
        con.close()

    return candidates


def candidate_paths_from_filesystem(
    codex_home: Path,
    date_text: str,
    timezone: tzinfo,
) -> dict[Path, dict[str, str | None]]:
    start, _ = date_window(date_text, timezone)
    candidates: dict[Path, dict[str, str | None]] = {}
    for delta in (-1, 0, 1):
        day = (start + timedelta(days=delta)).date()
        root = codex_home / "sessions" / str(day.year) / f"{day.month:02d}" / f"{day.day:02d}"
        if not root.exists():
            continue
        for path in sorted(root.glob("*.jsonl")):
            candidates.setdefault(path, {"source": "filesystem"})
    return candidates


def drop_inherited_context(messages: list[WorkMessage]) -> tuple[list[WorkMessage], int]:
    if not messages:
        return messages, 0

    first = min(message.timestamp for message in messages)
    first_burst_users = [
        message
        for message in messages
        if message.role == "user" and (message.timestamp - first).total_seconds() <= 2
    ]
    if len(first_burst_users) < 4:
        return messages, 0

    kept = [message for message in messages if (message.timestamp - first).total_seconds() > 2]
    return kept, len(messages) - len(kept)


def dedupe_messages(messages: list[WorkMessage]) -> list[WorkMessage]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[WorkMessage] = []
    for message in sorted(messages, key=lambda item: item.timestamp):
        key = (
            message.role,
            message.timestamp.replace(microsecond=0).isoformat(),
            message.text,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(message)
    return deduped


def parse_session_file(
    path: Path,
    date_text: str,
    workspace: Path,
    timezone: tzinfo,
    metadata: dict[str, str | None] | None = None,
    preview_limit: int = 5,
) -> ThreadSummary | None:
    start, end = date_window(date_text, timezone)
    metadata = metadata or {}
    thread_id = metadata.get("thread_id")
    title = metadata.get("title") or ""
    state_cwd = metadata.get("state_cwd") or ""
    source = metadata.get("source") or "filesystem"

    meta_cwd = ""
    event_messages: list[WorkMessage] = []
    fallback_messages: list[WorkMessage] = []

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None

    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if item.get("type") == "session_meta":
            payload = item.get("payload") or {}
            if isinstance(payload, dict):
                meta_cwd = str(payload.get("cwd") or meta_cwd)
                thread_id = thread_id or payload.get("id")

        timestamp = parse_timestamp(item.get("timestamp"), timezone)
        if not timestamp or not (start <= timestamp < end):
            continue

        if item.get("type") == "event_msg":
            payload = item.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            event_type = payload.get("type")
            if event_type not in ("user_message", "agent_message"):
                continue
            text = normalize_text(str(payload.get("message") or ""))
            if is_context_noise(text):
                continue
            role = "user" if event_type == "user_message" else "assistant"
            event_messages.append(WorkMessage(timestamp=timestamp, role=role, text=text))

        elif item.get("type") == "response_item":
            payload = item.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue
            text = normalize_text(text_from_response_content(payload.get("content")))
            if is_context_noise(text):
                continue
            fallback_messages.append(WorkMessage(timestamp=timestamp, role=str(role), text=text))

    cwd = meta_cwd or state_cwd
    if not in_workspace(cwd, workspace):
        return None

    raw_messages = event_messages if event_messages else fallback_messages
    raw_messages, inherited_dropped = drop_inherited_context(raw_messages)
    messages = dedupe_messages(raw_messages)
    if not messages:
        return None

    user_messages = [message for message in messages if message.role == "user"]
    if not user_messages:
        return None
    if is_report_thread(title, [message.text for message in user_messages]):
        return None

    return ThreadSummary(
        path=path,
        thread_id=str(thread_id) if thread_id else None,
        title=title,
        cwd=cwd,
        source=source,
        start=messages[0].timestamp,
        end=messages[-1].timestamp,
        user_messages=len(user_messages),
        assistant_messages=sum(1 for message in messages if message.role == "assistant"),
        inherited_context_messages_dropped=inherited_dropped,
        user_preview=user_messages[:preview_limit],
    )


def collect_threads(
    date_text: str,
    workspace: Path,
    codex_home: Path,
    timezone_name: str,
    preview_limit: int = 5,
) -> list[ThreadSummary]:
    timezone = resolve_timezone(timezone_name)
    candidates = candidate_paths_from_state(codex_home, date_text, workspace)
    for path, metadata in candidate_paths_from_filesystem(codex_home, date_text, timezone).items():
        candidates.setdefault(path, metadata)

    summaries: list[ThreadSummary] = []
    for path, metadata in sorted(candidates.items(), key=lambda item: str(item[0])):
        summary = parse_session_file(
            path=path,
            date_text=date_text,
            workspace=workspace,
            timezone=timezone,
            metadata=metadata,
            preview_limit=preview_limit,
        )
        if summary:
            summaries.append(summary)

    summaries.sort(key=lambda item: item.start or datetime.min.replace(tzinfo=timezone))
    return summaries
