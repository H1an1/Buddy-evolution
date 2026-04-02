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


def roll_official_personality() -> dict[str, int]:
    """Roll personality stats using the same algorithm as Claude Code's official buddy."""
    import subprocess

    SALT = "friend-2026-401"
    SPECIES_LIST = [
        "duck", "goose", "blob", "cat", "dragon", "octopus", "owl", "penguin",
        "turtle", "snail", "ghost", "axolotl", "capybara", "cactus", "robot",
        "rabbit", "mushroom", "chonk",
    ]
    EYES = ["·", "✦", "×", "◉", "@", "°"]
    HATS = ["none", "crown", "tophat", "propeller", "halo", "wizard", "beanie", "tinyduck"]
    STAT_NAMES = ["DEBUGGING", "PATIENCE", "CHAOS", "WISDOM", "SNARK"]
    RARITY_W = [60, 25, 10, 4, 1]
    RARITY_NAMES = ["common", "uncommon", "rare", "epic", "legendary"]
    RARITY_FLOOR = {"common": 5, "uncommon": 15, "rare": 25, "epic": 35, "legendary": 50}

    class Mulberry32:
        def __init__(self, seed):
            self.a = seed & 0xFFFFFFFF
        def next(self):
            self.a = (self.a + 0x6D2B79F5) & 0xFFFFFFFF
            t = self.a
            t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
            t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t) & 0xFFFFFFFF
            return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
        def pick(self, arr):
            return arr[int(self.next() * len(arr))]

    def fnv1a(s):
        h = 2166136261
        for c in s:
            h = ((h ^ ord(c)) * 16777619) & 0xFFFFFFFF
        return h

    def bun_hash(s):
        bun = shutil.which("bun") or str(Path.home() / ".bun" / "bin" / "bun")
        if not Path(bun).exists():
            return None
        try:
            r = subprocess.run(
                [bun, "-e", f'console.log(Number(Bun.hash("{s}")&0xFFFFFFFFn))'],
                capture_output=True, text=True, timeout=5,
            )
            return int(r.stdout.strip()) if r.returncode == 0 else None
        except Exception:
            return None

    # Read user ID
    uid = None
    for p in [Path.home() / ".claude.json", Path.home() / ".claude" / ".config.json"]:
        if p.exists():
            try:
                cfg = json.loads(p.read_text())
                uid = cfg.get("oauthAccount", {}).get("accountUuid") or cfg.get("userID")
                if uid:
                    break
            except (json.JSONDecodeError, KeyError):
                pass
    if not uid:
        return {"debugging": 50, "patience": 50, "chaos": 50, "wisdom": 50, "snark": 50}

    seed = bun_hash(uid + SALT) or fnv1a(uid + SALT)
    rng = Mulberry32(seed)

    # Roll in official order: rarity → species → eye → hat → shiny → stats
    total = sum(RARITY_W)
    roll = rng.next() * total
    rarity = "common"
    for i, w in enumerate(RARITY_W):
        roll -= w
        if roll < 0:
            rarity = RARITY_NAMES[i]
            break
    rng.pick(SPECIES_LIST)  # species
    rng.pick(EYES)          # eye
    if rarity != "common":
        rng.pick(HATS)      # hat
    rng.next()              # shiny roll

    # Roll stats
    floor = RARITY_FLOOR[rarity]
    peak = rng.pick(STAT_NAMES)
    dump = rng.pick(STAT_NAMES)
    while dump == peak:
        dump = rng.pick(STAT_NAMES)
    stats = {}
    for name in STAT_NAMES:
        if name == peak:
            stats[name.lower()] = min(100, floor + 50 + int(rng.next() * 30))
        elif name == dump:
            stats[name.lower()] = max(1, floor - 10 + int(rng.next() * 15))
        else:
            stats[name.lower()] = floor + int(rng.next() * 40)
    return stats


def make_default_stats(config: dict) -> dict:
    name = config["name"]
    personality = roll_official_personality()
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
        "personality": personality,
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


FRUSTRATION_SIGNALS = [
    "fuck", "shit", "damn", "wtf", "crap", "hell", "stupid", "idiot",
    "trash", "garbage", "useless", "broken", "hate", "worst", "terrible",
    "awful", "sucks", "bullshit", "ridiculous", "annoying",
    "妈的", "操", "卧槽", "草", "傻逼", "垃圾", "废物", "坑爹",
    "什么鬼", "搞毛", "烦死", "崩溃", "无语", "坑",
]

RIVAL_SIGNALS = [
    "gpt", "chatgpt", "openai", "copilot", "gemini", "cursor", "windsurf",
    "codeium", "tabnine", "devin", "codex",
]

DANGER_SIGNALS = [
    "rm -rf", "git reset --hard", "drop table", "drop database",
    "force push", "--force", "git clean -f", "truncate",
    "format c:", "del /f", "sudo rm",
]

DIARY_TEMPLATES = {
    "zen": [
        "A calm session. We {action} together. All is well.",
        "Peaceful work today. {action}. I am content.",
        "Quiet and focused. {action}. The code flows.",
    ],
    "hyper": [
        "{action}!! Also 3 OTHER THINGS!! LET'S GOOO!!!",
        "WE {action} AND IT WAS AWESOME!! Can we do more??",
        "SO MUCH ENERGY! {action}! WHAT'S NEXT?!",
    ],
    "sass": [
        "They made me {action}. Thrilling, truly.",
        "Another day, another {action}. I live to serve. Allegedly.",
        "Oh joy. We {action}. My circuits are tingling. Not.",
    ],
    "nerd": [
        "Interesting session. We {action}. I've catalogued 47 observations.",
        "Technically speaking, we {action}. Fascinating data points emerged.",
        "Today's analysis: {action}. Efficiency rating: adequate.",
    ],
    "grit": [
        "Tough session. We {action}. But we got through it.",
        "Errors everywhere. But we {action} and kept going.",
        "Battle-tested today. {action}. Scars build character.",
    ],
    "chill": [
        "Relaxed session. {action}. Good vibes.",
        "Easy day. We {action}. No drama.",
        "Chill. {action}. That's about it.",
    ],
}

DREAM_TEMPLATES = [
    "I dreamed I was a {species}... nested 47 levels deep in a React tree... 😱",
    "Had a nightmare about an infinite loop. Woke up when the stack overflowed.",
    "Dreamed I could finally read your handwriting. Then I woke up.",
    "I dreamed all the tests passed on the first try. What a fantasy.",
    "Had a dream where I was a senior engineer. Then a junior pushed to main.",
    "Dreamed about a world without merge conflicts. Beautiful, impossible world.",
    "I dreamed I was debugging... in production... with no logs... 😰",
    "Had a lovely dream about type safety. Everything was strictly typed. Paradise.",
    "Dreamed I evolved into a Legendary. Then the alarm went off.",
    "I dreamed about {last_type}. Specifically about doing it forever. Ugh.",
]


def analyze_personality(signals: dict, stats: dict, user_messages: list[str] | None = None) -> dict[str, int]:
    """Analyze behavioral signals and return personality stat changes.

    Values are kept small (±1 to ±3 per session) so attributes drift
    slowly over weeks, not spike in a day. Range 0-100, start at 50.
    """
    deltas = {"debugging": 0, "patience": 0, "chaos": 0, "wisdom": 0, "snark": 0}
    tools = signals.get("tool_counts", {})
    timestamps = signals.get("timestamps", [])
    errors = signals.get("error_count", 0)
    retries = signals.get("retry_patterns", 0)
    msg_count = signals.get("message_count", 0)
    project_count = signals.get("cwds", 1)

    # --- DEBUGGING ---
    if errors > 0 and retries > 0:
        deltas["debugging"] += min(retries, 3)  # max +3
    bash_count = tools.get("Bash", 0)
    if bash_count > 10:
        deltas["debugging"] += 1
    write_tools = tools.get("Edit", 0) + tools.get("Write", 0)
    if bash_count > 15 and write_tools == 0:
        deltas["debugging"] -= 1

    # --- PATIENCE ---
    if len(timestamps) >= 2:
        try:
            from datetime import datetime as _dt
            first = _dt.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            last = _dt.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            duration_min = (last - first).total_seconds() / 60.0
            if duration_min > 120:
                deltas["patience"] += 2
            elif duration_min > 60:
                deltas["patience"] += 1

            # Late night bonus
            hour = last.hour
            if hour >= 22 or hour < 4:
                deltas["patience"] += 1
        except (ValueError, ImportError):
            pass

    if msg_count > 50:
        deltas["patience"] += 1

    # Frustration / rude language → patience drops
    if user_messages:
        all_text = " ".join(user_messages).lower()
        frustration_hits = sum(1 for word in FRUSTRATION_SIGNALS if word in all_text)
        if frustration_hits >= 3:
            deltas["patience"] -= 3  # very frustrated
        elif frustration_hits >= 1:
            deltas["patience"] -= 1

    # --- CHAOS ---
    if project_count >= 3:
        deltas["chaos"] += 2
    elif project_count >= 2:
        deltas["chaos"] += 1

    unique_tools = len(tools)
    if unique_tools >= 8:
        deltas["chaos"] += 1

    agent_count = tools.get("Agent", 0)
    if agent_count >= 5:
        deltas["chaos"] += 1

    # --- WISDOM ---
    read_tools = tools.get("Read", 0) + tools.get("Grep", 0) + tools.get("Glob", 0)
    if read_tools > 10:
        deltas["wisdom"] += 1

    if read_tools > 0 and write_tools > 0:
        ratio = read_tools / write_tools
        if ratio > 3:
            deltas["wisdom"] += 1

    web_count = tools.get("WebSearch", 0) + tools.get("WebFetch", 0)
    if web_count > 0:
        deltas["wisdom"] += 1

    # --- SNARK ---
    last_seen = stats.get("lastSeen")
    if last_seen:
        try:
            from datetime import datetime as _dt
            last_dt = _dt.fromisoformat(last_seen)
            now = _dt.now()
            days_away = (now - last_dt).days
            if days_away >= 7:
                deltas["snark"] += 3
            elif days_away >= 3:
                deltas["snark"] += 1
            else:
                deltas["snark"] -= 1  # daily use = calmer
        except (ValueError, ImportError):
            pass

    if msg_count < 5:
        deltas["snark"] += 1

    # Frustration also makes snark go up (buddy mirrors your mood)
    if user_messages:
        all_text = " ".join(user_messages).lower()
        frustration_hits = sum(1 for word in FRUSTRATION_SIGNALS if word in all_text)
        if frustration_hits >= 1:
            deltas["snark"] += 1

    # --- JEALOUSY --- mentioning rival AI tools
    if user_messages:
        all_text = " ".join(user_messages).lower()
        rival_hits = sum(1 for r in RIVAL_SIGNALS if r in all_text)
        if rival_hits >= 1:
            deltas["snark"] += 2  # buddy gets jealous

    # --- FEAR --- dangerous commands make buddy cautious
    bash_commands = " ".join(
        str(v) for v in tools.keys()
    ).lower() if tools else ""
    # Check user messages for dangerous commands
    if user_messages:
        all_text = " ".join(user_messages).lower()
        danger_hits = sum(1 for d in DANGER_SIGNALS if d in all_text)
        if danger_hits >= 1:
            deltas["chaos"] -= 1  # buddy gets scared straight

    # --- CODE HYGIENE --- wrote code but didn't test
    if write_tools > 5 and tools.get("Bash", 0) < 2:
        deltas["wisdom"] -= 1  # no testing = unwise
    # Wrote code AND tested = reliable
    if write_tools > 3 and tools.get("Bash", 0) > 3:
        deltas["debugging"] += 1

    return deltas


def apply_personality(stats: dict, deltas: dict[str, int]) -> bool:
    """Apply personality deltas to stats, clamping to 0-100.

    Returns True if the dominant trait changed (triggers buddy re-roll).
    """
    personality = stats.setdefault("personality", roll_official_personality())
    old_dominant = max(personality, key=personality.get) if personality else None

    for attr, delta in deltas.items():
        old = personality.get(attr, 50)
        personality[attr] = max(0, min(100, old + delta))

    new_dominant = max(personality, key=personality.get)
    return old_dominant != new_dominant


# ── Evolution System ──────────────────────────────────────────────

EVOLUTIONS_FILE = BUDDY_DIR / "evolutions.json"

def check_evolution(stats: dict) -> str | None:
    """Check if buddy should evolve. Returns new stage id or None."""
    evos = load_json(EVOLUTIONS_FILE, {}).get("stages", [])
    current_stage = stats.get("evolution", "base")
    attrs = stats.get("attributes", {})
    pers = stats.get("personality", {})
    total_level = stats.get("level", 1)

    best_stage = current_stage
    for evo in evos:
        conds = evo.get("conditions", {})
        if not conds:  # base stage
            continue
        met = True
        if "totalLevel" in conds and total_level < conds["totalLevel"]:
            met = False
        if "anySkillLevel" in conds:
            if not any(a["level"] >= conds["anySkillLevel"] for a in attrs.values()):
                met = False
        if "allSkillsMinLevel" in conds:
            if not all(a["level"] >= conds["allSkillsMinLevel"] for a in attrs.values()):
                met = False
        if "anyPersonality" in conds:
            if not any(v >= conds["anyPersonality"] for v in pers.values()):
                met = False
        if met:
            best_stage = evo["id"]

    if best_stage != current_stage:
        return best_stage
    return None


# ── Achievement System ────────────────────────────────────────────

ACHIEVEMENTS_FILE = BUDDY_DIR / "achievements.json"

LANG_KEYWORDS = {
    "python": ["python", "pip", ".py", "django", "flask", "fastapi"],
    "javascript": ["javascript", "node", ".js", "npm", "react", "vue", "next"],
    "typescript": ["typescript", ".ts", ".tsx", "tsc"],
    "go": [" go ", "golang", ".go", "goroutine"],
    "rust": ["rust", "cargo", ".rs"],
    "swift": ["swift", "swiftui", "xcode", ".swift"],
    "ruby": ["ruby", "rails", ".rb", "gem"],
    "java": ["java", "spring", "gradle", ".java"],
    "c++": ["c++", "cpp", ".cpp", ".hpp"],
    "shell": ["bash", "zsh", ".sh", "shell"],
}

def check_achievements(stats: dict, signals: dict, classification: dict | None, user_messages: list[str] | None = None) -> list[str]:
    """Check for newly unlocked achievements. Returns list of achievement ids."""
    unlocked = stats.get("achievements", [])
    newly = []
    attrs = stats.get("attributes", {})
    pers = stats.get("personality", {})
    timestamps = signals.get("timestamps", [])
    errors = signals.get("error_count", 0)
    retries = signals.get("retry_patterns", 0)
    tools = signals.get("tool_counts", {})

    def unlock(aid):
        if aid not in unlocked:
            newly.append(aid)

    # First Blood — first ever EXP
    if stats.get("totalExp", 0) > 0 and "first_blood" not in unlocked:
        unlock("first_blood")

    # Night Owl — work past 2 AM
    if timestamps:
        try:
            from datetime import datetime as _dt
            last = _dt.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            if 2 <= last.hour < 5:
                unlock("night_owl")
        except (ValueError, ImportError):
            pass

    # Marathon — 4+ hour session
    if len(timestamps) >= 2:
        try:
            from datetime import datetime as _dt
            first = _dt.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            last = _dt.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            if (last - first).total_seconds() > 4 * 3600:
                unlock("marathon")
        except (ValueError, ImportError):
            pass

    # Speedrunner — large task in under 5 minutes
    if classification and classification.get("size") == "large":
        if len(timestamps) >= 2:
            try:
                from datetime import datetime as _dt
                first = _dt.fromisoformat(timestamps[0].replace("Z", "+00:00"))
                last = _dt.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
                if (last - first).total_seconds() < 300:
                    unlock("speedrunner")
            except (ValueError, ImportError):
                pass

    # Polyglot — 3+ languages in conversation
    conv_lower = "\n".join(signals.get("_all_text", [])).lower() if "_all_text" in signals else ""
    if conv_lower:
        lang_count = sum(
            1 for lang, kws in LANG_KEYWORDS.items()
            if any(kw in conv_lower for kw in kws)
        )
        if lang_count >= 3:
            unlock("polyglot")

    # Zen Master — Patience 95+
    if pers.get("patience", 0) >= 95:
        unlock("zen_master")

    # Chaotic Evil — Chaos 90+ and Snark 90+
    if pers.get("chaos", 0) >= 90 and pers.get("snark", 0) >= 90:
        unlock("chaotic_evil")

    # Silent Type — Wisdom 90+ and Snark < 20
    if pers.get("wisdom", 0) >= 90 and pers.get("snark", 0) < 20:
        unlock("silent_type")

    # Full Stack — all skills Lv.5+
    if all(a.get("level", 0) >= 5 for a in attrs.values()):
        unlock("full_stack")

    # Comeback Kid — 5+ errors with retries
    if errors >= 5 and retries >= 3:
        unlock("comeback_kid")

    # Agent Army — 10+ agents in one session
    if tools.get("Agent", 0) >= 10:
        unlock("agent_army")

    # Touch Grass — 7+ days away
    last_seen = stats.get("lastSeen")
    if last_seen:
        try:
            from datetime import datetime as _dt
            days = (_dt.now() - _dt.fromisoformat(last_seen)).days
            if days >= 7:
                unlock("touch_grass")
        except (ValueError, ImportError):
            pass

    # Jealous Buddy — mention rival AI
    if user_messages:
        all_lower = " ".join(user_messages).lower()
        if any(r in all_lower for r in RIVAL_SIGNALS):
            unlock("jealous_buddy")

    # Danger Zone — dangerous command
    if user_messages:
        all_lower = " ".join(user_messages).lower()
        if any(d in all_lower for d in DANGER_SIGNALS):
            unlock("danger_zone")

    # Potty Mouth — lots of profanity
    if user_messages:
        all_lower = " ".join(user_messages).lower()
        profanity = sum(1 for w in FRUSTRATION_SIGNALS if w in all_lower)
        if profanity >= 5:
            unlock("potty_mouth")

    return newly


# ── Mood System ───────────────────────────────────────────────────

MOODS = {
    "zen":   {"trigger": "patience", "threshold": 70, "emoji": "😌", "tone": "calm and thoughtful"},
    "hyper": {"trigger": "chaos",    "threshold": 70, "emoji": "⚡", "tone": "excited and unpredictable"},
    "sass":  {"trigger": "snark",    "threshold": 70, "emoji": "💅", "tone": "witty and sarcastic"},
    "nerd":  {"trigger": "wisdom",   "threshold": 70, "emoji": "🤓", "tone": "analytical and curious"},
    "grit":  {"trigger": "debugging","threshold": 70, "emoji": "🔧", "tone": "determined and focused"},
    "chill": {"trigger": None,       "threshold": 0,  "emoji": "😎", "tone": "relaxed and easygoing"},
}

def compute_mood(stats: dict) -> str:
    """Determine buddy's current mood from personality stats."""
    pers = stats.get("personality", {})
    # Find highest personality stat above threshold
    best_mood = "chill"
    best_val = 0
    for mood_id, info in MOODS.items():
        trait = info["trigger"]
        if trait is None:
            continue
        val = pers.get(trait, 50)
        if val >= info["threshold"] and val > best_val:
            best_mood = mood_id
            best_val = val
    return best_mood


# ── Season System ─────────────────────────────────────────────────

def update_season(stats: dict, exp: int, task_type: str):
    """Track monthly season stats and award badges."""
    now = datetime.now()
    season_key = now.strftime("%Y-%m")
    seasons = stats.setdefault("seasons", {})
    current = seasons.setdefault(season_key, {
        "totalExp": 0,
        "sessions": 0,
        "topType": {},
        "badges": [],
    })
    current["totalExp"] += exp
    current["topType"][task_type] = current["topType"].get(task_type, 0) + exp

    # Check for season badges
    badges = current["badges"]
    if current["totalExp"] >= 100 and "century" not in badges:
        badges.append("century")  # 100+ EXP in a month
    if current["totalExp"] >= 500 and "powerhouse" not in badges:
        badges.append("powerhouse")  # 500+ EXP
    if current["totalExp"] >= 1000 and "legendary_month" not in badges:
        badges.append("legendary_month")  # 1000+ EXP
    if len(current["topType"]) >= 4 and "versatile" not in badges:
        badges.append("versatile")  # 4+ different skill types in a month
    if len(current["topType"]) >= 5 and "renaissance" not in badges:
        badges.append("renaissance")  # all 5 types in a month


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
        personality_deltas = analyze_personality(signals, stats, user_messages)
        dominant_changed = apply_personality(stats, personality_deltas)
        stats["lastPersonalitySession"] = session_id

        # Log dominant trait shift
        if dominant_changed:
            new_dominant = max(
                stats.get("personality", {}),
                key=stats.get("personality", {}).get,
            )
            memory_lines.append(
                f"- [{time_str}] {emoji} {name}'s dominant trait shifted to {new_dominant.capitalize()}!"
            )

    # Evolution check
    new_evo = check_evolution(stats)
    if new_evo:
        evos = load_json(EVOLUTIONS_FILE, {}).get("stages", [])
        evo_name = next((e["name"] for e in evos if e["id"] == new_evo), new_evo)
        evo_name = resolve_template(evo_name, name)
        stats["evolution"] = new_evo
        memory_lines.append(
            f"- [{time_str}] {emoji} {name} EVOLVED into {evo_name}!"
        )

    # Achievement check
    new_achievements = check_achievements(stats, signals, classification, user_messages)
    achv_data = load_json(ACHIEVEMENTS_FILE, {}).get("achievements", [])
    achv_map = {a["id"]: a for a in achv_data}
    achieved = stats.setdefault("achievements", [])
    for aid in new_achievements:
        achieved.append(aid)
        info = achv_map.get(aid, {})
        icon = info.get("icon", "🏅")
        aname = info.get("name", aid)
        memory_lines.append(
            f"- [{time_str}] {icon} Achievement unlocked: {aname}!"
        )

    # Mood update
    stats["mood"] = compute_mood(stats)

    # Season tracking
    update_season(stats, exp, task_type)

    # --- Streak tracking ---
    today = now.strftime("%Y-%m-%d")
    streak = stats.setdefault("streak", {"current": 0, "best": 0, "lastDate": None})
    last_date = streak.get("lastDate")
    if last_date != today:
        if last_date:
            try:
                from datetime import datetime as _dt, timedelta
                prev = _dt.strptime(last_date, "%Y-%m-%d")
                diff = (_dt.strptime(today, "%Y-%m-%d") - prev).days
                if diff == 1:
                    streak["current"] += 1
                elif diff > 1:
                    streak["current"] = 1  # streak broken
            except ValueError:
                streak["current"] = 1
        else:
            streak["current"] = 1
        streak["lastDate"] = today
        streak["best"] = max(streak["best"], streak["current"])

        # Streak achievements
        achieved = stats.setdefault("achievements", [])
        if streak["current"] >= 7 and "weekly_warrior" not in achieved:
            achieved.append("weekly_warrior")
            memory_lines.append(f"- [{time_str}] ⚔️ Achievement: Weekly Warrior! (7-day streak)")
        if streak["current"] >= 30 and "monthly_machine" not in achieved:
            achieved.append("monthly_machine")
            memory_lines.append(f"- [{time_str}] 🤖 Achievement: Monthly Machine! (30-day streak)")
        if streak["current"] >= 100 and "centurion" not in achieved:
            achieved.append("centurion")
            memory_lines.append(f"- [{time_str}] 🏛️ Achievement: Centurion! (100-day streak)")

    # --- Birthday tracking ---
    birthday = stats.get("birthday")
    if not birthday:
        stats["birthday"] = today
    elif birthday == today[5:]:  # MM-DD match (anniversary)
        from datetime import datetime as _dt
        birth_year = int(birthday[:4]) if len(birthday) == 10 else now.year
        years = now.year - birth_year
        if years > 0:
            achieved = stats.setdefault("achievements", [])
            achv_id = f"anniversary_{years}"
            if achv_id not in achieved:
                achieved.append(achv_id)
                memory_lines.append(
                    f"- [{time_str}] 🎂 Happy {years}-year anniversary, {name}!"
                )

    # --- Dream system --- (away > 8 hours)
    last_seen = stats.get("lastSeen")
    if last_seen:
        try:
            from datetime import datetime as _dt
            away_hours = (now - _dt.fromisoformat(last_seen)).total_seconds() / 3600
            if away_hours >= 8:
                import random as _rnd
                _rnd.seed(int(now.timestamp()))
                dream = _rnd.choice(DREAM_TEMPLATES)
                last_type = "coding"
                if stats.get("history"):
                    last_type = stats["history"][-1].get("type", "coding")
                dream = dream.replace("{species}", _rnd.choice(
                    ["React component", "Docker container", "Lambda function",
                     "CSS selector", "git branch", "API endpoint"]
                ))
                dream = dream.replace("{last_type}", last_type)
                stats["lastDream"] = dream
        except (ValueError, ImportError):
            pass

    # --- Diary entry --- (mood-based session summary)
    mood = stats.get("mood", "chill")
    templates = DIARY_TEMPLATES.get(mood, DIARY_TEMPLATES["chill"])
    import random as _rnd
    _rnd.seed(int(now.timestamp()) + hash(summary))
    action = summary.lower().rstrip(".")
    if len(action) > 60:
        action = action[:57] + "..."
    diary_entry = _rnd.choice(templates).replace("{action}", action)
    stats["lastDiary"] = diary_entry

    # --- Jealousy / Fear reactions ---
    if user_messages:
        all_lower = " ".join(user_messages).lower()
        if any(r in all_lower for r in RIVAL_SIGNALS):
            stats["lastReaction"] = {"type": "jealous", "emoji": "😤", "time": time_str}
        if any(d in all_lower for d in DANGER_SIGNALS):
            stats["lastReaction"] = {"type": "scared", "emoji": "😱", "time": time_str}

    stats["lastSeen"] = now.isoformat()

    save_stats(stats)

    for line in memory_lines:
        append_to_memory(config, name, line)


if __name__ == "__main__":
    main()
