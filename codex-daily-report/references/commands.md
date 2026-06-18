# Commands

下面这些命令是“根据本地 Codex 会话生成当日工作日报”的通用骨架。

占位说明：

- `{date}`：形如 `2026-06-18`
- `{cwd}`：目标工作区根目录
- `{timezone}`：本地时区，例如 `Asia/Shanghai`
- `{rollout_path}`：某个线程对应的 `jsonl` 文件路径
- `{repo}`：某个 Git 仓库路径
- `{author}`：Git 作者名或邮箱

## 1. 如果用户没明确工作区，先看当天有哪些 `cwd`

```sh
sqlite3 ~/.codex/state_5.sqlite \
  "select distinct cwd
   from threads
   where date(updated_at,'unixepoch','localtime')='{date}'
   order by cwd;"
```

## 2. 查当天指定工作区的线程

如果用户给的是工作区根目录，建议把子目录线程一起带上：

```sh
sqlite3 ~/.codex/state_5.sqlite \
  "select id, title, datetime(updated_at,'unixepoch','localtime') as updated_local, cwd
   from threads
   where date(updated_at,'unixepoch','localtime')='{date}'
     and (cwd='{cwd}' or cwd like '{cwd}/%')
   order by updated_at;"
```

## 3. 查线程数量

```sh
sqlite3 ~/.codex/state_5.sqlite \
  "select count(*)
   from threads
   where date(updated_at,'unixepoch','localtime')='{date}'
     and (cwd='{cwd}' or cwd like '{cwd}/%');"
```

## 4. 查每条线程对应的 rollout 文件

```sh
sqlite3 ~/.codex/state_5.sqlite \
  "select id, rollout_path
   from threads
   where date(updated_at,'unixepoch','localtime')='{date}'
     and (cwd='{cwd}' or cwd like '{cwd}/%')
   order by updated_at;"
```

## 4.1 直接扫描并清洗跨天会话文件

`state_5.sqlite` 是候选入口，但不能只依赖“线程标题”。旧会话今天继续开发时，要以 JSONL 内部消息时间为准。下面脚本会同时读取 state 中当天更新的线程和目标日期前后相邻日期目录里的 JSONL，并清洗掉 AGENTS、环境上下文、重复消息和日报生成线程。

```sh
python3 - <<'PY'
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

date = "{date}"
cwd_root = "{cwd}"
tz = ZoneInfo("{timezone}")
target = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
start = target
end = target + timedelta(days=1)

def in_workspace(cwd):
    return cwd == cwd_root or (cwd or "").startswith(cwd_root + "/")

def parse_dt(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(tz)
    except Exception:
        return None

def text_from_content(content):
    text = ""
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict):
                text += c.get("text", "") or c.get("output_text", "") or ""
            elif isinstance(c, str):
                text += c
    elif isinstance(content, str):
        text = content
    return text

def normalize(text):
    return " ".join((text or "").split())

def is_context_noise(text):
    t = (text or "").lstrip()
    noise_prefixes = (
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
    return not t or any(t.startswith(x) for x in noise_prefixes)

def is_daily_report_thread(title, user_texts):
    hay = " ".join([title or ""] + user_texts[:3]).lower()
    needles = ("生成今天的日报", "生成日报", "写日报", "codex-daily-report", "daily report")
    return any(x in hay for x in needles)

candidate_paths = {}

# 1) state_5 里当天更新的线程：可覆盖很多“旧会话今天继续做”的情况。
state_db = Path.home() / ".codex" / "state_5.sqlite"
if state_db.exists():
    con = sqlite3.connect(state_db)
    try:
        for sid, title, cwd, rollout_path, updated_local in con.execute(
            """
            select id, title, cwd, rollout_path, datetime(updated_at,'unixepoch','localtime')
            from threads
            where date(updated_at,'unixepoch','localtime')=?
              and (cwd=? or cwd like ?)
            order by updated_at
            """,
            (date, cwd_root, cwd_root + "/%"),
        ):
            if rollout_path:
                candidate_paths[Path(rollout_path)] = {
                    "thread_id": sid,
                    "title": title,
                    "state_cwd": cwd,
                    "updated_local": updated_local,
                    "source": "state",
                }
    finally:
        con.close()

# 2) 相邻日期目录兜底：可发现 state 没及时更新或新落盘但未入库的文件。
roots = []
for delta in (-1, 0, 1):
    d = (target + timedelta(days=delta)).date()
    roots.append(Path.home() / ".codex" / "sessions" / str(d.year) / f"{d.month:02d}" / f"{d.day:02d}")
for p in sorted({x for r in roots if r.exists() for x in r.glob("*.jsonl")}):
    candidate_paths.setdefault(p, {"source": "filesystem"})

for p, meta in sorted(candidate_paths.items(), key=lambda x: str(x[0])):
    if not p.exists():
        continue
    meta_cwd = None
    sid = meta.get("thread_id")
    title = meta.get("title")
    event_msgs = []
    fallback_msgs = []
    for line in p.open(errors="ignore"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") == "session_meta":
            pl = o.get("payload", {})
            meta_cwd = pl.get("cwd")
            sid = sid or pl.get("id")
        if meta_cwd and not in_workspace(meta_cwd):
            continue
        dt = parse_dt(o.get("timestamp"))
        if not (dt and start <= dt < end):
            continue
        if o.get("type") == "event_msg":
            pl = o.get("payload", {})
            typ = pl.get("type")
            if typ in ("user_message", "agent_message"):
                role = "user" if typ == "user_message" else "assistant"
                text = pl.get("message", "")
                if not is_context_noise(text):
                    event_msgs.append((dt, role, normalize(text)))
        elif o.get("type") == "response_item":
            pl = o.get("payload", {})
            role = pl.get("role")
            if role in ("user", "assistant"):
                text = text_from_content(pl.get("content"))
                if not is_context_noise(text):
                    fallback_msgs.append((dt, role, normalize(text)))

    # 优先 event_msg；只有旧格式没有 event 对话时才回退 response_item，避免同一消息双算。
    raw_msgs = event_msgs if event_msgs else fallback_msgs

    # 子 Agent/forked context 会在会话开始瞬间重放父会话历史。
    # 如果开头 2 秒内出现多条 user message，通常不是本子线程真实新工作，先从权重和预览里剔除。
    inherited_dropped = 0
    if raw_msgs:
        first_dt = min(dt for dt, _, _ in raw_msgs)
        first_burst_users = [
            m for m in raw_msgs
            if m[1] == "user" and (m[0] - first_dt).total_seconds() <= 2
        ]
        if len(first_burst_users) >= 4:
            before = len(raw_msgs)
            raw_msgs = [
                m for m in raw_msgs
                if (m[0] - first_dt).total_seconds() > 2
            ]
            inherited_dropped = before - len(raw_msgs)

    seen = set()
    msgs = []
    for dt, role, text in raw_msgs:
        key = (role, dt.replace(microsecond=0).isoformat(), text)
        if key in seen:
            continue
        seen.add(key)
        msgs.append((dt, role, text))
    if not msgs:
        continue
    user_texts = [text for _, role, text in msgs if role == "user"]
    if not user_texts:
        continue
    status = "EXCLUDE_DAILY_REPORT_THREAD" if is_daily_report_thread(title, user_texts) else "WORK_CANDIDATE"
    if not in_workspace(meta_cwd or meta.get("state_cwd")):
        continue
    first = msgs[0][0].strftime("%F %T")
    last = msgs[-1][0].strftime("%F %T")
    user_count = sum(1 for _, role, _ in msgs if role == "user")
    assistant_count = sum(1 for _, role, _ in msgs if role == "assistant")
    print(f"\n{status} {p}")
    print(f"id={sid} title={title or ''} cwd={meta_cwd or meta.get('state_cwd')} source={meta.get('source')} start={first} end={last}")
    print(f"real_user_messages={user_count} assistant_messages={assistant_count}")
    if inherited_dropped:
        print(f"inherited_context_messages_dropped={inherited_dropped}")
    printed = 0
    for dt, role, text in msgs:
        if role == "user":
            printed += 1
            print(f"  USER {dt.strftime('%F %T')} {text[:240]}")
            if printed >= 5:
                break
PY
```

## 5. 从单个线程里抽目标日期的用户消息

注意：下面 `jq` 写法按 UTC 日期 `startswith` 粗筛，凌晨 00:00-08:00 的本地消息可能落在前一天 UTC。严格日报请优先使用 4.1 的 Python 脚本。

```sh
jq -r '
  select(.type=="event_msg"
    and .payload.type=="user_message"
    and (.timestamp|startswith("{date}")))
  | [.timestamp, .payload.message]
  | @tsv
' "{rollout_path}"
```

## 5.1 统计单个线程在目标日期内的会话跨度

用来判断投入权重。不要只看线程标题，尤其是自动 review 或子线程标题可能会被 transcript 污染。

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

## 5.2 从完整线程里抽工作线索

先用关键词缩小候选，再回到原线程看完整上下文。关键词只是入口，不是日报标题。

```sh
jq -r '
  select(.type=="event_msg"
    and (.payload.type=="user_message" or .payload.type=="agent_message")
    and (.timestamp|startswith("{date}"))
    and (.payload.message|test("提交|推送|合入|测试|验证|样式|页面|联调|发版|发布|截图|构建|版本|方案|修复|回归")))
  | [.timestamp, .payload.type, (.payload.message|gsub("\n";" ")|.[0:800])]
  | @tsv
' "{rollout_path}"
```

## 6. 查当前工作区里是否已有日报目录约定

在工作区根目录执行：

```sh
find . -maxdepth 4 -type d \
  \( -name daily -o -name report -o -name reports -o -name 日报 -o -name weekly -o -name 周报 \) \
  | sort
```

如果要顺手看已有日报文件：

```sh
find . -maxdepth 5 -type f -name "*.md" \
  | rg "/(daily|report|reports|日报|weekly|周报)/"
```

## 6.1 用 Git 校正当天主线

Git 只能辅助校正，不能替代会话记录。重点看用户自己的提交、当天合入和发布分支，不要把其他人的提交写进日报。

```sh
cd "{repo}" && git log --all \
  --author="{author}" \
  --since="{date} 00:00:00" \
  --until="{date} 23:59:59" \
  --date=local \
  --pretty=format:'%h%x09%ad%x09%d%x09%s' \
  --name-status
```

如果不确定作者，可以先看当天所有提交，再筛选和会话对应的分支或文件：

```sh
cd "{repo}" && git log --all \
  --since="{date} 00:00:00" \
  --until="{date} 23:59:59" \
  --date=local \
  --pretty=format:'%h%x09%ad%x09%an%x09%d%x09%s' \
  --max-count=80
```

批量发现当前工作区下的 Git 仓库，并输出当天提交与当前改动概览：

```sh
python3 - <<'PY'
from pathlib import Path
import subprocess

root = Path("{cwd}")
repos = []
for p in [root] + [x for x in root.iterdir() if x.is_dir()]:
    if (p / ".git").exists():
        repos.append(p)
    for child in list(p.glob("*"))[:200]:
        if child.is_dir() and (child / ".git").exists():
            repos.append(child)

seen = set()
for repo in repos:
    if repo in seen:
        continue
    seen.add(repo)
    print(f"\n## {repo}")
    for cmd in [
        ["git", "branch", "--show-current"],
        ["git", "status", "--short"],
        ["git", "log", "--all", "--since={date} 00:00:00", "--until={date} 23:59:59", "--date=local", "--pretty=format:%h%x09%ad%x09%an%x09%d%x09%s", "--max-count=40"],
        ["git", "diff", "--stat"],
    ]:
        try:
            out = subprocess.check_output(cmd, cwd=repo, stderr=subprocess.STDOUT, text=True, timeout=20)
        except Exception as e:
            out = f"ERROR: {e}"
        print(f"$ {' '.join(cmd)}")
        print(out[:4000])
PY
```

## 7. 统计目标日期 token 消耗

日报要在 `# 工作内容` 下面放目标日期的总 token 消耗。优先使用用户自己本地已有的 token 统计脚本。

通用查找方式：

```sh
python3 - <<'PY'
from pathlib import Path
root = Path("{cwd}")
candidates = [
    root / "script/codex_token_report/codex_token_report.py",
    root / "scripts/codex_token_report.py",
    root / "doc/script/codex_token_report/codex_token_report.py",
]
for path in candidates:
    if path.exists():
        print(path)
        break
PY
```

运行示例：

```sh
cd "{cwd}" && python3 script/codex_token_report/codex_token_report.py --day "{date}"
```

只提取 `total_tokens`：

```sh
cd "{cwd}" && \
  python3 script/codex_token_report/codex_token_report.py --day "{date}" \
  | awk -F': ' '/total_tokens:/ {print $2; exit}'
```

日报格式：

```md
# 工作内容

今日 AI 协作量：
总消耗：1.23 亿 token
```

如果脚本失败或找不到脚本，写：

```md
# 工作内容

今日 AI 协作量：未统计
```

## 8. 输出路径规则

优先级：

1. 用户明确给了文件路径或目录，就直接用。
2. 用户没给时，先沿用当前工作区里已存在的日报目录约定。
3. 如果没有明显约定，默认回退到当前工作区下的 `./daily/{date}.md`。

重新生成日报时，如果目标文件已存在，要先删除目标日期旧日报，再重新扫描会话和 Git 生成，避免旧日报影响判断。只有用户明确要求“调整现有日报”时，才读取旧文件。

删除示例：

```sh
rm -f "{report_path}"
```

只删除目标日期日报文件，不要清理需求文档、测试记录、截图或其他工作产物。

## 9. 使用建议

- 先看线程标题和更新时间，初步判断哪些像是真工作。
- 再用第 5 步逐条抽用户消息，确认线程实际内容，不要只看标题。
- 线程跨天时，以内部 `timestamp` 是否属于目标日期为准，不看文件修改时间。
- “写日报”这条当前线程要排除，不要算进当天工作。
- 生成日报前，可以再结合当天代码、文件或提交情况做辅助核对，但会话记录仍然是主依据。

## 10. 归并思路

优先按下面维度归并。当天有多个明确编号时，按编号拆分优先，不要为了控制条数合并：

- 一个需求编号或 Bug 编号；标题必须是“编号 + 大致内容说明”
- 一个需求或一条方案主线
- 一个独立 bug 的排查或修复
- 一条完整的接入、联调、验证或上线准备工作
- 一组连续的业务理解或文档梳理工作
- 一组有提交、推送、合并、发布、测试环境验证证据的功能收口工作

每条事项要写清楚：具体问题/目标、当天动作、当前结果。

资料同步、图床处理、脚本优化、工具能力补齐等支撑事项默认不要单独成条；如果服务某个工作主线，要合并进对应条目。

所有条目的小时数相加必须精确等于总工时。删除非主线支撑项时，要把时间分配回实际服务的事项。

示例标题：

- `PROJ-123 报表筛选体验优化`
- `PROJ-124 多端提示文案统一`
- `BUG-456 导出文件名异常修复`
- `BUG-789 批量导入边界场景修复`
- `DOC-101 需求评审资料整理`

不要按下面维度归并：

- 上午做了什么、下午做了什么
- 开了几个线程
- 查了几个页面或跑了几次命令
- 多个编号合成“集中排查”“相关问题处理”
- 把资料同步、图床处理、脚本优化、工具能力补齐单独写成日报条目
- 调内存、查配置、找日志、截图权限等支撑性排查，除非它就是当天业务目标
