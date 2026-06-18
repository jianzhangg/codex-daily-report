from __future__ import annotations

import re
import shlex
import subprocess

TOKEN_RE = re.compile(r"(?:单日\s*)?total_tokens\s*[:：]\s*([0-9][0-9,]*)", re.IGNORECASE)


def parse_total_tokens(text: str) -> int | None:
    match = TOKEN_RE.search(text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def run_token_command(command: str | None, timeout: int = 60) -> int | None:
    if not command:
        return None
    try:
        result = subprocess.run(
            shlex.split(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return parse_total_tokens(result.stdout + "\n" + result.stderr)


def format_token_total(total: int | None) -> str:
    if total is None:
        return "未统计"
    if total >= 100_000_000:
        return f"{total / 100_000_000:.2f} 亿 token"
    if total >= 10_000:
        return f"{total / 10_000:.2f} 万 token"
    return f"{total:,} token"
