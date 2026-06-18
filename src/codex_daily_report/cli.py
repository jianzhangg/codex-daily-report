from __future__ import annotations

import argparse
from pathlib import Path

from .codex_sessions import collect_threads
from .git_activity import collect_git_activity, today_text
from .models import ReportContext
from .render import render_markdown
from .token_usage import run_token_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-daily-report",
        description="从本机 Codex 会话记录和 Git 活动生成中文日报素材草稿。",
    )
    parser.add_argument("--date", default=today_text(), help="目标日期，格式 YYYY-MM-DD，默认今天。")
    parser.add_argument(
        "--workspace",
        default=".",
        help="目标工作区，默认当前目录。会扫描该目录及其子目录里的会话和 Git 仓库。",
    )
    parser.add_argument("--hours", type=float, default=8.0, help="计划工时，默认 8。")
    parser.add_argument("--output", help="输出 Markdown 文件路径。不传时打印到标准输出。")
    parser.add_argument("--codex-home", default="~/.codex", help="Codex 数据目录，默认 ~/.codex。")
    parser.add_argument("--timezone", default="local", help="时区名称，默认 local，也可传 Asia/Shanghai。")
    parser.add_argument("--preview-limit", type=int, default=5, help="每个会话展示的用户消息预览数量。")
    parser.add_argument("--git-depth", type=int, default=2, help="向下发现 Git 仓库的最大目录深度。")
    parser.add_argument("--no-git", action="store_true", help="不扫描 Git 活动。")
    parser.add_argument(
        "--token-command",
        help="可选 token 统计命令。输出中出现 total_tokens: 123,456 时会被解析。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    codex_home = Path(args.codex_home).expanduser().resolve()

    threads = collect_threads(
        date_text=args.date,
        workspace=workspace,
        codex_home=codex_home,
        timezone_name=args.timezone,
        preview_limit=args.preview_limit,
    )
    git_repos = [] if args.no_git else collect_git_activity(workspace, args.date, max_depth=args.git_depth)
    token_total = run_token_command(args.token_command)

    context = ReportContext(
        date=args.date,
        workspace=workspace,
        hours=args.hours,
        token_total=token_total,
        threads=threads,
        git_repos=git_repos,
    )
    markdown = render_markdown(context)

    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
