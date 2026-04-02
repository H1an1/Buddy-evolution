#!/usr/bin/env python3
"""Claude Buddy — RPG upgrade system for your Claude Code companion.

Reads a Claude Code conversation transcript, classifies the task,
awards EXP, handles level-ups, and optionally logs to a daily memory file.
"""

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

BUDDY_DIR = Path.home() / ".claude" / "buddy"
CONFIG_FILE = BUDDY_DIR / "config.json"
STATS_FILE = BUDDY_DIR / "stats.json"
TITLES_FILE = BUDDY_DIR / "titles.json"
PHRASES_FILE = BUDDY_DIR / "phrases.json"

EXP_RANGES = {"small": (5, 10), "medium": (15, 25), "large": (30, 50)}
ATTR_LEVEL_COST = 50
TOTAL_LEVEL_COST = 200


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_config() -> dict:
    defaults = {
        "name": "Buddy",
        "emoji": "\U0001f916",
        "memory_dir": None,
        "memory_template": "# {date} Log\n\n## Summary\n",
        "memory_marker": "## Summary",
    }
    config = load_json(CONFIG_FILE, {})
    for k, v in defaults.items():
        config.setdefault(k, v)
    return config


def make_default_stats(config: dict) -> dict:
    name = config["name"]
    return {
        "name": name,
        "level": 1,
        "totalExp": 0,
        "attributes": {
            "coding":   {"exp": 0, "level": 1},
            "design":   {"exp": 0, "level": 1},
            "research": {"exp": 0, "level": 1},
            "devops":   {"exp": 0, "level": 1},
            "writing":  {"exp": 0, "level": 1},
        },
        "personality": {
            "debugging": 50,
            "patience":  50,
            "chaos":     50,
            "wisdom":    50,
            "snark":     50,
        },
        "titles": [f"Baby {name}"],
        "activeTitle": f"Baby {name}",
        "unlocked": ["total_1"],
        "history": [],
        "lastSeen": None,
    }


def save_stats(stats: dict):
    if STATS_FILE.exists():
        shutil.copy2(STATS_FILE, STATS_FILE.with_suffix(".json.bak"))
    STATS_FILE.write_text(json.dumps(stats, indent=2, ensure_ascii=False))


def extract_conversation(transcript_path: str) -> tuple[str, list[str], dict]:
    """Extract conversation text, user messages, and behavioral signals.

    Returns (full_text, user_messages, signals) where signals is a dict of
    behavioral data for personality analysis.
    """
    texts = []
    user_messages = []
    signals = {
        "timestamps": [],       # all message timestamps
        "tool_counts": {},      # tool_name -> count
        "error_count": 0,       # tool errors
        "retry_patterns": 0,    # same tool called after error
        "message_count": 0,     # total messages
        "user_turns": 0,        # user message count
        "cwds": set(),          # unique working directories (project switching)
        "session_id": None,     # session identifier for dedup
    }
    last_tool_errored = None

    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    msg_type = obj.get("type")

                    # Collect timestamps
                    ts = obj.get("timestamp")
                    if ts:
                        signals["timestamps"].append(ts)

                    # Collect working directories
                    cwd = obj.get("cwd")
                    if cwd:
                        signals["cwds"].add(cwd)

                    # Capture session ID (same for all messages in a session)
                    sid = obj.get("sessionId")
                    if sid and not signals["session_id"]:
                        signals["session_id"] = sid

                    if msg_type == "user":
                        signals["user_turns"] += 1
                        content = obj.get("message", {}).get("content", [])
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text = item.get("text", "").strip()
                                if text:
                                    texts.append(text)
                                    user_messages.append(text)
                            elif isinstance(item, str) and item.strip():
                                texts.append(item.strip())
                                user_messages.append(item.strip())

                    elif msg_type == "assistant":
                        signals["message_count"] += 1
                        content = obj.get("message", {}).get("content", [])
                        for item in content:
                            if not isinstance(item, dict):
                                if isinstance(item, str) and item.strip():
                                    texts.append(item.strip())
                                continue
                            if item.get("type") == "text":
                                text = item.get("text", "").strip()
                                if text:
                                    texts.append(text)
                            elif item.get("type") == "tool_use":
                                tool_name = item.get("name", "unknown")
                                signals["tool_counts"][tool_name] = (
                                    signals["tool_counts"].get(tool_name, 0) + 1
                                )
                                # Check retry pattern
                                if tool_name == last_tool_errored:
                                    signals["retry_patterns"] += 1
                                    last_tool_errored = None
                            elif item.get("type") == "tool_result":
                                if item.get("is_error"):
                                    signals["error_count"] += 1
                                    # Track which tool errored for retry detection
                                    last_tool_errored = item.get("tool_use_id")

                except (json.JSONDecodeError, AttributeError):
                    pass
    except FileNotFoundError:
        pass

    signals["cwds"] = len(signals["cwds"])  # convert set to count
    return "\n".join(texts[-30:]), user_messages, signals


def pick_summary(user_messages: list[str]) -> str:
    """Pick the best user message as summary."""
    MIN_LENGTH = 8
    candidates = [
        msg for msg in user_messages
        if len(msg) >= MIN_LENGTH and not msg.startswith("<")
    ]
    if not candidates:
        if user_messages:
            return max(user_messages, key=len)[:80]
        return "Task completed"
    return max(candidates, key=len)[:80]


def analyze_personality(signals: dict, stats: dict) -> dict[str, int]:
    """Analyze behavioral signals and return personality stat changes.

    Returns a dict of {attribute: delta} where delta can be positive or negative.
    Each attribute is clamped to 0-100 after applying.

    Personality attributes:
      debugging  — retry patterns, error→success arcs, tool diversity
      patience   — long sessions, late night work, high message counts
      chaos      — project switching, many sessions/day, unpredictable patterns
      wisdom     — Read/Grep heavy, code reading vs writing ratio
      snark      — grows when absent, shrinks with frequent use
    """
    deltas = {"debugging": 0, "patience": 0, "chaos": 0, "wisdom": 0, "snark": 0}
    tools = signals.get("tool_counts", {})
    timestamps = signals.get("timestamps", [])
    errors = signals.get("error_count", 0)
    retries = signals.get("retry_patterns", 0)
    msg_count = signals.get("message_count", 0)
    project_count = signals.get("cwds", 1)

    # --- DEBUGGING ---
    # Errors followed by retries = persistence in debugging
    if errors > 0 and retries > 0:
        # Breakthrough bonus: failed then succeeded
        deltas["debugging"] += min(retries * 3, 15)
    # Bash usage (running commands, testing) helps debugging
    bash_count = tools.get("Bash", 0)
    if bash_count > 5:
        deltas["debugging"] += 2
    # Only running commands without writing code → debugging drops
    write_tools = tools.get("Edit", 0) + tools.get("Write", 0)
    if bash_count > 10 and write_tools == 0:
        deltas["debugging"] -= 2

    # --- PATIENCE ---
    # Session duration
    if len(timestamps) >= 2:
        try:
            from datetime import datetime as _dt
            first = _dt.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            last = _dt.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            duration_min = (last - first).total_seconds() / 60.0
            if duration_min > 120:
                deltas["patience"] += 5  # 2+ hours = very patient
            elif duration_min > 60:
                deltas["patience"] += 3
            elif duration_min > 30:
                deltas["patience"] += 1

            # Late night bonus (22:00-04:00 local time)
            hour = last.hour  # UTC, but still a signal
            if hour >= 22 or hour < 4:
                deltas["patience"] += 2  # burning the midnight oil
        except (ValueError, ImportError):
            pass

    # High message count = sticking with it
    if msg_count > 50:
        deltas["patience"] += 3
    elif msg_count > 20:
        deltas["patience"] += 1

    # --- CHAOS ---
    # Multiple projects in one session
    if project_count >= 3:
        deltas["chaos"] += 5
    elif project_count >= 2:
        deltas["chaos"] += 2

    # Many tool types used = chaotic energy
    unique_tools = len(tools)
    if unique_tools >= 8:
        deltas["chaos"] += 3
    elif unique_tools >= 5:
        deltas["chaos"] += 1

    # Agent spawning = parallel chaos
    agent_count = tools.get("Agent", 0)
    if agent_count >= 3:
        deltas["chaos"] += 3

    # --- WISDOM ---
    # Reading code (Read, Grep, Glob) vs writing (Edit, Write)
    read_tools = tools.get("Read", 0) + tools.get("Grep", 0) + tools.get("Glob", 0)
    if read_tools > 10:
        deltas["wisdom"] += 3
    elif read_tools > 5:
        deltas["wisdom"] += 1

    # High read-to-write ratio = studying, not just hacking
    if read_tools > 0 and write_tools > 0:
        ratio = read_tools / write_tools
        if ratio > 3:
            deltas["wisdom"] += 3  # mostly reading = wise
        elif ratio > 1.5:
            deltas["wisdom"] += 1

    # WebSearch/WebFetch = seeking knowledge
    web_count = tools.get("WebSearch", 0) + tools.get("WebFetch", 0)
    if web_count > 0:
        deltas["wisdom"] += 2

    # --- SNARK ---
    # Snark grows with absence, shrinks with presence
    last_seen = stats.get("lastSeen")
    if last_seen:
        try:
            from datetime import datetime as _dt
            last_dt = _dt.fromisoformat(last_seen)
            now = _dt.now()
            days_away = (now - last_dt).days
            if days_away >= 7:
                deltas["snark"] += 8   # gone a week? very snarky
            elif days_away >= 3:
                deltas["snark"] += 4
            elif days_away >= 1:
                deltas["snark"] += 1
            else:
                deltas["snark"] -= 1   # using it daily = less snarky
        except (ValueError, ImportError):
            pass

    # Short sessions = buddy gets bored = snarky
    if msg_count < 5:
        deltas["snark"] += 2

    return deltas


def apply_personality(stats: dict, deltas: dict[str, int]):
    """Apply personality deltas to stats, clamping to 0-100."""
    personality = stats.setdefault("personality", {
        "debugging": 50, "patience": 50, "chaos": 50,
        "wisdom": 50, "snark": 50,
    })
    for attr, delta in deltas.items():
        old = personality.get(attr, 50)
        personality[attr] = max(0, min(100, old + delta))


KEYWORDS = {
    "coding": [
        "bug", "fix", "code", "function", "implement", "refactor", "component",
        "error", "debug", "test", "commit", "merge", "PR", "pull request",
        "typescript", "python", "javascript", "react", "swift", "API",
        "endpoint", "database", "query", "schema", "migration", "import",
        "export", "class", "module", "package", "dependency", "npm", "git",
        "build", "compile", "lint", "type", "interface", "hook", "state",
        "render", "animation", "layout", "route", "middleware", "server",
        "client", "fetch", "async", "promise", "callback", "variable",
    ],
    "design": [
        "design", "figma", "mockup", "wireframe", "prototype", "UI", "UX",
        "color", "font", "typography", "layout", "spacing", "pixel", "icon",
        "illustration", "sketch", "artboard", "style guide", "theme",
        "responsive", "mobile", "desktop", "breakpoint", "grid", "card",
        "shadow", "border", "gradient", "palette", "brand", "visual",
        "poster", "banner", "logo", "pen file", ".pen",
    ],
    "research": [
        "research", "investigate", "explore", "analyze", "compare",
        "documentation", "docs", "search", "find", "look up", "check",
        "evaluate", "review", "assess", "benchmark", "study", "learn",
        "understand", "explain", "how does", "what is", "why does",
        "alternative", "option", "approach", "strategy", "brainstorm",
    ],
    "devops": [
        "deploy", "deployment", "CI/CD", "pipeline", "docker", "container",
        "kubernetes", "k8s", "server", "infrastructure", "AWS", "cloud",
        "terraform", "nginx", "SSL", "certificate", "domain", "DNS",
        "monitoring", "log", "alert", "uptime", "scaling", "load balancer",
        "environment", "staging", "production", "config", "secret", "env var",
        "vercel", "netlify", "hosting", "cron", "backup", "restore",
    ],
    "writing": [
        "write", "document", "readme", "changelog", "blog", "article",
        "post", "draft", "edit", "proofread", "translate", "content",
        "copy", "text", "paragraph", "section", "outline", "summary",
        "report", "proposal", "spec", "specification", "plan", "RFC",
        "newsletter", "email", "message", "announcement", "note", "memo",
    ],
}

CHAT_SIGNALS = [
    "hello", "hi", "hey", "thanks", "thank you", "bye", "good morning",
    "how are you", "what's up", "nice", "cool", "ok", "okay", "got it",
]

SIZE_SIGNALS = {
    "large": [
        "architect", "redesign", "rewrite", "new project", "scaffold",
        "migration", "overhaul", "major", "system", "full", "complete",
        "from scratch", "rebuild", "rearchitect", "plan", "spec",
    ],
    "small": [
        "quick", "small", "tiny", "minor", "tweak", "typo", "rename",
        "simple", "one-line", "config", "setting", "flag", "toggle",
    ],
}


def classify_task(conversation: str) -> dict | None:
    if not conversation or len(conversation) < 50:
        return None
    text_lower = conversation.lower()
    words = text_lower.split()
    if len(words) < 20:
        chat_count = sum(1 for s in CHAT_SIGNALS if s in text_lower)
        if chat_count >= len(words) // 3:
            return None
    scores = {}
    for category, kws in KEYWORDS.items():
        scores[category] = sum(1 for kw in kws if kw.lower() in text_lower)
    if max(scores.values()) == 0:
        return None
    return {"type": max(scores, key=scores.get), "size": _detect_size(text_lower)}


def _detect_size(text_lower: str) -> str:
    for sz in ("large", "small"):
        if any(signal in text_lower for signal in SIZE_SIGNALS[sz]):
            return sz
    return "medium"


def calc_exp(size: str) -> int:
    lo, hi = EXP_RANGES.get(size, (5, 10))
    return (lo + hi) // 2


def compute_level(exp: int, cost_per_level: int) -> int:
    level = 1
    cumulative = 0
    while True:
        needed = level * cost_per_level
        if cumulative + needed > exp:
            break
        cumulative += needed
        level += 1
    return level


def resolve_template(text: str, name: str) -> str:
    """Replace {name} placeholders in title/phrase strings."""
    return text.replace("{name}", name)


def check_title_unlock(titles_data: dict, attr: str, new_level: int) -> str | None:
    attr_titles = titles_data.get("attributes", {}).get(attr, {})
    return attr_titles.get(str(new_level))


def check_total_title(titles_data: dict, new_level: int) -> str | None:
    return titles_data.get("total", {}).get(str(new_level))


def check_phrase_unlock(phrases_data: dict, key: str) -> str | None:
    return phrases_data.get(key)


def append_to_memory(config: dict, name: str, line: str):
    """Append a line to today's memory file if memory_dir is configured."""
    memory_dir_str = config.get("memory_dir")
    if not memory_dir_str:
        return

    memory_dir = Path(os.path.expanduser(memory_dir_str))
    if not memory_dir.is_dir():
        return

    now = datetime.now()
    filename = f"{now.strftime('%Y-%m-%d')}-memory.md"
    memory_file = memory_dir / filename

    if not memory_file.exists():
        template = config.get("memory_template", "# {date} Log\n\n## Summary\n")
        memory_file.write_text(template.replace("{date}", now.strftime("%Y-%m-%d")))

    content = memory_file.read_text()
    marker = config.get("memory_marker", "## Summary")
    if marker in content:
        idx = content.index(marker) + len(marker)
        newline_idx = content.index("\n", idx)
        content = content[:newline_idx] + "\n" + line + content[newline_idx:]
    else:
        content += "\n" + line + "\n"

    memory_file.write_text(content)


def main():
    if len(sys.argv) < 2:
        sys.exit(0)

    transcript_path = sys.argv[1]
    if not transcript_path or not os.path.isfile(transcript_path):
        sys.exit(0)

    config = load_config()
    name = config["name"]
    emoji = config["emoji"]

    conversation, user_messages, signals = extract_conversation(transcript_path)
    classification = classify_task(conversation)
    if classification is None:
        sys.exit(0)

    task_type = classification["type"]
    task_size = classification["size"]
    summary = pick_summary(user_messages)
    exp = calc_exp(task_size)

    default_stats = make_default_stats(config)
    stats = load_json(STATS_FILE, default_stats)
    for key, val in default_stats.items():
        stats.setdefault(key, val if not isinstance(val, dict) else val.copy())
    for attr in default_stats["attributes"]:
        stats["attributes"].setdefault(attr, {"exp": 0, "level": 1})

    titles_data = load_json(TITLES_FILE, {"attributes": {}, "total": {}})
    phrases_data = load_json(PHRASES_FILE, {})

    attr_data = stats["attributes"][task_type]
    old_attr_level = attr_data["level"]
    attr_data["exp"] += exp
    new_attr_level = compute_level(attr_data["exp"], ATTR_LEVEL_COST)
    attr_data["level"] = new_attr_level

    stats["totalExp"] += exp
    old_total_level = stats["level"]
    new_total_level = compute_level(stats["totalExp"], TOTAL_LEVEL_COST)
    stats["level"] = new_total_level

    now = datetime.now()
    time_str = now.strftime("%H:%M")
    memory_lines = []
    attr_leveled_up = new_attr_level > old_attr_level
    total_leveled_up = new_total_level > old_total_level

    if attr_leveled_up:
        title = check_title_unlock(titles_data, task_type, new_attr_level)
        if title:
            title = resolve_template(title, name)
            if title not in stats["titles"]:
                stats["titles"].append(title)
                stats["activeTitle"] = title
        phrase_key = f"{task_type}_{new_attr_level}"
        phrase = check_phrase_unlock(phrases_data, phrase_key)
        if phrase and phrase_key not in stats["unlocked"]:
            stats["unlocked"].append(phrase_key)

    if total_leveled_up:
        total_title = check_total_title(titles_data, new_total_level)
        if total_title:
            total_title = resolve_template(total_title, name)
            if total_title not in stats["titles"]:
                stats["titles"].append(total_title)
                stats["activeTitle"] = total_title
        total_phrase_key = f"total_{new_total_level}"
        total_phrase = check_phrase_unlock(phrases_data, total_phrase_key)
        if total_phrase and total_phrase_key not in stats["unlocked"]:
            stats["unlocked"].append(total_phrase_key)

    type_display = task_type.capitalize()
    if attr_leveled_up:
        title_str = check_title_unlock(titles_data, task_type, new_attr_level) or ""
        title_str = resolve_template(title_str, name)
        title_part = f' "{title_str}"' if title_str else ""
        memory_line = f"- [{time_str}] {emoji} {name} +{exp} {type_display} EXP (Lv.{old_attr_level}\u2192{new_attr_level}!{title_part}) \u2014 {summary}"
    else:
        memory_line = f"- [{time_str}] {emoji} {name} +{exp} {type_display} EXP \u2014 {summary}"
    memory_lines.append(memory_line)

    if total_leveled_up:
        tt = check_total_title(titles_data, new_total_level) or ""
        tt = resolve_template(tt, name)
        memory_lines.append(f"- [{time_str}] {emoji} {name} Total Lv.{old_total_level}\u2192{new_total_level}! \"{tt}\"")

    stats["history"].append({
        "date": now.strftime("%Y-%m-%d"),
        "time": time_str,
        "type": task_type,
        "exp": exp,
        "summary": summary,
    })

    if len(stats["history"]) > 200:
        stats["history"] = stats["history"][-200:]

    # Personality update — only once per session to avoid stacking
    session_id = signals.get("session_id")
    last_personality_session = stats.get("lastPersonalitySession")
    if session_id and session_id != last_personality_session:
        personality_deltas = analyze_personality(signals, stats)
        apply_personality(stats, personality_deltas)
        stats["lastPersonalitySession"] = session_id
    stats["lastSeen"] = now.isoformat()

    save_stats(stats)

    for line in memory_lines:
        append_to_memory(config, name, line)


if __name__ == "__main__":
    main()
