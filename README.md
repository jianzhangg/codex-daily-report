# Codex Daily Report

从本机 Codex 会话记录、目标工作区 Git 活动和可选 token 统计里提取当天工作素材，生成一份中文 Markdown 日报草稿。

这个项目是一个通用开源版本，只保留本地解析和写作骨架，不包含任何公司内部流程、需求系统、数据库口径、真实工单编号或固定个人路径。

## 能做什么

- 扫描 `~/.codex/state_5.sqlite` 和 `~/.codex/sessions/**/{date}/*.jsonl`
- 按工作区过滤当天相关 Codex 会话
- 识别跨天继续推进的会话
- 清理 `AGENTS.md instructions`、环境上下文、重复 `response_item` 等噪音
- 汇总目标工作区及子目录 Git 仓库当天提交、状态和 diff 概览
- 可选接入你自己的 token 统计命令
- 输出一份适合继续交给 Codex 或人工改写的中文 Markdown 草稿
- 附带一个脱敏版 Codex skill，可直接作为个人 skill 的起点

## 安装

```sh
python3 -m pip install .
```

开发模式：

```sh
python3 -m pip install -e .
```

## 使用

在目标工作区执行：

```sh
codex-daily-report --date 2026-06-18 --workspace . --hours 8 --output daily/2026-06-18.md
```

如果不传日期，默认使用当前本地日期：

```sh
codex-daily-report --workspace .
```

指定时区：

```sh
codex-daily-report --timezone Asia/Shanghai --workspace .
```

接入自定义 token 统计脚本：

```sh
codex-daily-report \
  --date 2026-06-18 \
  --workspace . \
  --token-command "python3 scripts/token_report.py --day 2026-06-18"
```

## 输出定位

CLI 默认输出的是“日报素材草稿”，不是假装已经完全理解业务语境的最终日报。它会把候选会话、Git 活动和写作提示组织好，让你或 Codex 基于真实素材再压缩成管理者可读的工作日报。

推荐流程：

1. 先用 CLI 生成素材草稿。
2. 人工或 Codex 检查候选会话是否有漏项。
3. 把草稿压缩成正式日报，保留业务目标、关键动作和当前结果。

## 隐私说明

这个工具默认只在本机读取文件，不会联网，也不会把会话内容上传到任何服务。生成的 Markdown 可能包含你的会话片段、提交信息、分支名或文件名，公开分享前请自行复核和脱敏。

## Codex skill

脱敏版 skill 放在：

```text
skills/codex-daily-report/
```

你可以把这个目录复制到自己的 Codex skills 目录，再按个人工作流修改写作口径。公开版本里没有绑定任何特定公司或需求系统。

## 开发

运行测试：

```sh
python3 -m unittest discover -s tests
```

运行一次本地草稿生成：

```sh
python3 -m codex_daily_report.cli --workspace . --date 2026-06-18
```

## 许可证

MIT
