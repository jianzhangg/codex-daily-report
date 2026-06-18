from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from codex_daily_report.codex_sessions import collect_threads, is_context_noise, normalize_text
from codex_daily_report.token_usage import parse_total_tokens


class CodexSessionTests(unittest.TestCase):
    def test_normalize_text(self) -> None:
        self.assertEqual(normalize_text("  a\n b\tc  "), "a b c")

    def test_context_noise(self) -> None:
        self.assertTrue(is_context_noise("# AGENTS.md instructions\nabc"))
        self.assertTrue(is_context_noise("<environment_context>"))
        self.assertFalse(is_context_noise("请帮我修复导出问题"))

    def test_parse_total_tokens(self) -> None:
        self.assertEqual(parse_total_tokens("单日 total_tokens: 123,456,789"), 123456789)
        self.assertEqual(parse_total_tokens("total_tokens: 42"), 42)
        self.assertIsNone(parse_total_tokens("no token here"))

    def test_collect_threads_from_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            codex_home = root / ".codex"
            session_dir = codex_home / "sessions" / "2026" / "06" / "18"
            session_dir.mkdir(parents=True)
            rollout = session_dir / "rollout.jsonl"
            rows = [
                {
                    "type": "session_meta",
                    "payload": {"id": "thread-1", "cwd": str(workspace)},
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-18T02:00:00Z",
                    "payload": {"type": "user_message", "message": "请帮我整理今天的功能验证结果"},
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-18T02:01:00Z",
                    "payload": {"type": "agent_message", "message": "已开始整理。"},
                },
            ]
            rollout.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")

            summaries = collect_threads(
                date_text="2026-06-18",
                workspace=workspace,
                codex_home=codex_home,
                timezone_name="UTC",
            )

            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].thread_id, "thread-1")
            self.assertEqual(summaries[0].user_messages, 1)
            self.assertEqual(summaries[0].assistant_messages, 1)

    def test_collect_threads_from_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            codex_home = root / ".codex"
            session_dir = codex_home / "sessions" / "2026" / "06" / "18"
            session_dir.mkdir(parents=True)
            rollout = session_dir / "rollout.jsonl"
            rollout.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "session_meta", "payload": {"id": "thread-2", "cwd": str(workspace)}}),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "timestamp": "2026-06-18T04:00:00Z",
                                "payload": {"type": "user_message", "message": "继续推进报表筛选优化"},
                            },
                            ensure_ascii=False,
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            db_path = codex_home / "state_5.sqlite"
            con = sqlite3.connect(db_path)
            try:
                con.execute(
                    "create table threads (id text, title text, cwd text, rollout_path text, updated_at integer)"
                )
                con.execute(
                    "insert into threads values (?, ?, ?, ?, ?)",
                    ("thread-2", "PROJ-123 报表筛选", str(workspace), str(rollout), 1781740800),
                )
                con.commit()
            finally:
                con.close()

            summaries = collect_threads(
                date_text="2026-06-18",
                workspace=workspace,
                codex_home=codex_home,
                timezone_name="UTC",
            )

            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].title, "PROJ-123 报表筛选")


if __name__ == "__main__":
    unittest.main()
