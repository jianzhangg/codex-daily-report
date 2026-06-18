from __future__ import annotations

from .models import ReportContext
from .token_usage import format_token_total


def render_markdown(context: ReportContext) -> str:
    lines: list[str] = [
        "# 工作内容",
        "",
        "今日 AI 协作量：",
        f"总消耗：{format_token_total(context.token_total)}",
        f"计划工时：{context.hours:g}h",
        "",
        "> 以下是根据本机 Codex 会话和 Git 活动自动整理的日报素材草稿。正式提交前，请继续压缩成业务目标、关键动作和当前结果。",
        "",
        "## 候选会话",
        "",
    ]

    if not context.threads:
        lines.append("未发现目标日期内匹配当前工作区的 Codex 会话。")
    else:
        for index, thread in enumerate(context.threads, start=1):
            start = thread.start.strftime("%Y-%m-%d %H:%M:%S") if thread.start else "-"
            end = thread.end.strftime("%Y-%m-%d %H:%M:%S") if thread.end else "-"
            title = thread.title or "(无标题)"
            lines.extend(
                [
                    f"**{index}. {title}**",
                    f"- 时间：{start} ~ {end}",
                    f"- 消息：用户 {thread.user_messages} 条，助手 {thread.assistant_messages} 条",
                    f"- 工作区：`{thread.cwd}`",
                    f"- 会话文件：`{thread.path}`",
                ]
            )
            if thread.inherited_context_messages_dropped:
                lines.append(f"- 已忽略继承上下文：{thread.inherited_context_messages_dropped} 条")
            if thread.user_preview:
                lines.append("- 用户消息预览：")
                for message in thread.user_preview:
                    preview = message.text[:220]
                    lines.append(f"  - {message.timestamp.strftime('%H:%M:%S')} {preview}")
            lines.append("")

    lines.extend(["## Git 活动", ""])
    if not context.git_repos:
        lines.append("未发现目标日期内的提交或当前未提交改动。")
    else:
        for repo in context.git_repos:
            lines.append(f"**{repo.path}**")
            if repo.branch:
                lines.append(f"- 当前分支：`{repo.branch}`")
            if repo.status:
                lines.append("- 未提交改动：")
                for row in repo.status.splitlines()[:20]:
                    lines.append(f"  - `{row}`")
            if repo.commits:
                lines.append("- 当天提交：")
                for commit in repo.commits:
                    lines.append(f"  - `{commit.hash}` {commit.subject}（{commit.author}，{commit.date}）")
            if repo.diff_stat:
                lines.append("- Diff 概览：")
                for row in repo.diff_stat.splitlines()[:20]:
                    lines.append(f"  - `{row}`")
            lines.append("")

    lines.extend(
        [
            "## 写作提示",
            "",
            "- 先按真实工作主线归并，不按会话数量逐条罗列。",
            "- 每条保留问题或目标、当天动作、当前结果。",
            "- 技术细节只保留能说明交付质量的部分。",
            "- 工时合计需要等于计划工时。",
            "- 公开分享前检查会话片段、提交信息、路径和文件名是否需要脱敏。",
            "",
        ]
    )

    return "\n".join(lines)
