# Commands

这些命令是“根据本机 Codex 会话生成当日工作日报素材”的通用骨架。

占位说明：

- `{date}`：形如 `2026-06-18`
- `{cwd}`：目标工作区根目录
- `{rollout_path}`：某个线程对应的 JSONL 文件路径

## 查询当天工作区线程

```sh
sqlite3 ~/.codex/state_5.sqlite \
  "select id, title, datetime(updated_at,'unixepoch','localtime') as updated_local, cwd, rollout_path
   from threads
   where date(updated_at,'unixepoch','localtime')='{date}'
   order by updated_at;"
```

## 抽取单个线程的用户消息

```sh
jq -r '
  select(.type=="event_msg"
    and .payload.type=="user_message"
    and (.timestamp|startswith("{date}")))
  | [.timestamp, .payload.message]
  | @tsv
' "{rollout_path}"
```

## 统计单个线程在目标日期内的会话跨度

```sh
jq -s -r '
  [
    .[]
    | select(.type=="event_msg"
      and (.payload.type=="user_message" or .payload.type=="agent_message")
      and (.timestamp|startswith("{date}")))
  ] as $msgs
  | select($msgs|length>0)
  | {
      start: $msgs[0].timestamp,
      end: $msgs[-1].timestamp,
      user_messages: ($msgs|map(select(.payload.type=="user_message"))|length),
      agent_messages: ($msgs|map(select(.payload.type=="agent_message"))|length),
      total_messages: ($msgs|length)
    }
' "{rollout_path}"
```

## 查找日报目录

```sh
find . -maxdepth 4 -type d \
  \( -name daily -o -name report -o -name reports -o -name 日报 \) \
  | sort
```

## 扫描 Git 活动

```sh
git log --all \
  --since="{date} 00:00:00" \
  --until="{date} 23:59:59" \
  --date=local \
  --pretty=format:'%h%x09%ad%x09%an%x09%s' \
  --max-count=80
```

```sh
git status --short
git diff --stat
```

## 使用内置 CLI

```sh
codex-daily-report --date "{date}" --workspace "{cwd}" --hours 8 --output "daily/{date}.md"
```
