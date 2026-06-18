# Codex Daily Report Skill

这是一个可直接复制安装的 Codex skill，用来根据本机 Codex 会话记录、目标工作区 Git 活动和可选 token 统计整理中文日报或周报。

这个仓库只保留 skill 本体和示例文件，不需要 Python 安装，不需要构建，也不绑定任何公司内部系统。

## 目录结构

```text
codex-daily-report/
  SKILL.md
  references/commands.md
  agents/openai.yaml
examples/
  daily.example.md
README.md
LICENSE
```

文件说明：

- `codex-daily-report/SKILL.md`：核心 skill 说明，包含完整日报/周报生成规则、筛选规则、写作规则和自检清单。
- `codex-daily-report/references/commands.md`：查询本机 Codex 会话、JSONL、Git 活动和 token 统计的参考命令。
- `codex-daily-report/agents/openai.yaml`：Codex 插件界面展示和默认提示词。
- `examples/daily.example.md`：脱敏日报示例。

## 安装

把整个 `codex-daily-report/` 目录复制到你的 Codex skills 目录即可：

```sh
cp -R codex-daily-report ~/.codex/skills/
```

安装后可以在 Codex 里这样使用：

```text
使用 $codex-daily-report 生成今天的日报
```

或指定日期、工作区和工时：

```text
使用 $codex-daily-report 生成 2026-06-18 的日报，工作区是 /path/to/workspace，总工时 8h
```

## 它会做什么

- 默认读取 `~/.codex/state_5.sqlite` 和 `~/.codex/sessions/.../*.jsonl`。
- 按目标工作区筛选当天相关会话。
- 处理跨天继续推进的旧会话。
- 过滤 `AGENTS.md instructions`、环境上下文、重复消息和日报生成线程。
- 结合 Git 当天提交、未提交改动和文件变动校正工作主线。
- 可选读取 token 统计结果，写入“今日 AI 协作量”。
- 按真实工作主线生成中文日报或周报。

## 脱敏说明

这个公开版本来自一个真实个人工作流，但已经做了通用化处理：

- 删除了公司名、内部系统名、真实需求编号、真实业务案例和固定个人路径。
- 把私有需求系统改写为通用的 Issue/Bug tracker。
- 把专属进度口径改写成可选的通用校正规则。
- 保留了原始工作流里更重要的部分：跨天会话扫描、Git 校正、消息去噪、主线归并、工时拆分和成稿自检。

如果你有自己的公司流程，建议在本地复制一份私有规则，不要直接提交到公开仓库。

## 隐私提醒

这个 skill 的参考命令只读取本机文件，不会主动联网。生成日报时仍可能引用你的会话片段、提交信息、分支名、文件路径或内部编号，公开分享前请自行复核和脱敏。

## 许可证

MIT
