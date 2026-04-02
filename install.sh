#!/bin/bash
# Claude Buddy — Install Script
# Sets up the RPG upgrade system for your Claude Code companion
set -e

BUDDY_DIR="$HOME/.claude/buddy"
HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🤖 Claude Buddy — Installer"
echo ""

# Ask for buddy name
read -p "What's your buddy's name? (default: Buddy): " BUDDY_NAME
BUDDY_NAME="${BUDDY_NAME:-Buddy}"

# Ask for emoji
read -p "Pick an emoji for $BUDDY_NAME (default: 🤖): " BUDDY_EMOJI
BUDDY_EMOJI="${BUDDY_EMOJI:-🤖}"

# Auto-detect species from user ID hash (same algorithm as Claude Code)
echo ""
echo "Detecting your buddy's species..."
BUDDY_SPECIES=""
# Output JSON: {"species": "...", "stats": {"debugging": N, ...}}
DETECTED_JSON=$(python3 -c "
import json, pathlib, subprocess, shutil

SALT = 'friend-2026-401'
SPECIES = ['duck','goose','blob','cat','dragon','octopus','owl','penguin',
           'turtle','snail','ghost','axolotl','capybara','cactus','robot',
           'rabbit','mushroom','chonk']
EYES = ['·','✦','×','◉','@','°']
HATS = ['none','crown','tophat','propeller','halo','wizard','beanie','tinyduck']
STAT_NAMES = ['DEBUGGING','PATIENCE','CHAOS','WISDOM','SNARK']
RARITY_W = [60, 25, 10, 4, 1]
RARITY_FLOOR = {'common': 5, 'uncommon': 15, 'rare': 25, 'epic': 35, 'legendary': 50}

def fnv1a(s):
    h = 2166136261
    for c in s:
        h = ((h ^ ord(c)) * 16777619) & 0xFFFFFFFF
    return h

def bun_hash(s):
    bun = shutil.which('bun') or str(pathlib.Path.home() / '.bun' / 'bin' / 'bun')
    if not pathlib.Path(bun).exists():
        return None
    try:
        r = subprocess.run([bun, '-e', f'console.log(Number(Bun.hash(\"{s}\")&0xFFFFFFFFn))'],
                           capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip()) if r.returncode == 0 else None
    except:
        return None

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

uid = None
for p in [pathlib.Path.home()/'.claude.json', pathlib.Path.home()/'.claude'/'.config.json']:
    if p.exists():
        try:
            cfg = json.loads(p.read_text())
            uid = cfg.get('oauthAccount',{}).get('accountUuid') or cfg.get('userID')
            if uid: break
        except: pass
if not uid:
    raise SystemExit(1)

seed = bun_hash(uid + SALT) or fnv1a(uid + SALT)
rng = Mulberry32(seed)

# Roll in official order: rarity → species → eye → hat → shiny → stats
total = sum(RARITY_W)
roll = rng.next() * total
rarity = 'common'
for i, w in enumerate(RARITY_W):
    roll -= w
    if roll < 0:
        rarity = ['common','uncommon','rare','epic','legendary'][i]
        break
species = rng.pick(SPECIES)
eye = rng.pick(EYES)
hat = 'none' if rarity == 'common' else rng.pick(HATS)
shiny = rng.next() < 0.01

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

print(json.dumps({'species': species, 'stats': stats}))
" 2>/dev/null)

DETECTED_SPECIES=""
if [[ -n "$DETECTED_JSON" ]]; then
    DETECTED_SPECIES=$(echo "$DETECTED_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['species'])")
fi

if [[ -n "$DETECTED_SPECIES" ]]; then
    echo "  Detected: $DETECTED_SPECIES"
    read -p "Keep $DETECTED_SPECIES? [Y/n]: " KEEP_SPECIES
    if [[ -z "$KEEP_SPECIES" || "$KEEP_SPECIES" =~ ^[Yy] ]]; then
        BUDDY_SPECIES="$DETECTED_SPECIES"
    fi
fi

if [[ -z "$BUDDY_SPECIES" ]]; then
    echo "  Could not auto-detect. Run /buddy in Claude Code to check yours."
    echo "  Species: duck, goose, blob, cat, dragon, octopus, owl, penguin,"
    echo "           turtle, snail, ghost, axolotl, capybara, cactus, robot,"
    echo "           rabbit, mushroom, chonk"
    read -p "  Enter species: " BUDDY_SPECIES
fi

# Ask for memory dir
echo ""
echo "Optional: daily memory log integration."
echo "If you use a daily notes system (Obsidian, etc), enter the directory."
echo "Leave blank to skip."
read -p "Memory directory (blank to skip): " MEMORY_DIR

echo ""
echo "Setting up $BUDDY_EMOJI $BUDDY_NAME..."

# Create directories
mkdir -p "$BUDDY_DIR"
mkdir -p "$HOOKS_DIR"

# Copy files
cp "$SCRIPT_DIR/update.py" "$BUDDY_DIR/update.py"
cp "$SCRIPT_DIR/titles.json" "$BUDDY_DIR/titles.json"
cp "$SCRIPT_DIR/phrases.json" "$BUDDY_DIR/phrases.json"
cp "$SCRIPT_DIR/statusline.sh" "$BUDDY_DIR/statusline.sh"
cp "$SCRIPT_DIR/evolutions.json" "$BUDDY_DIR/evolutions.json"
cp "$SCRIPT_DIR/achievements.json" "$BUDDY_DIR/achievements.json"
cp "$SCRIPT_DIR/buddy-hook.sh" "$HOOKS_DIR/buddy-hook.sh"

chmod +x "$BUDDY_DIR/update.py"
chmod +x "$BUDDY_DIR/statusline.sh"
chmod +x "$HOOKS_DIR/buddy-hook.sh"

# Write config
if [[ -n "$MEMORY_DIR" ]]; then
    MEMORY_JSON="\"$(echo "$MEMORY_DIR" | sed 's/"/\\"/g')\""
else
    MEMORY_JSON="null"
fi

if [[ -n "$BUDDY_SPECIES" ]]; then
    SPECIES_JSON="\"$BUDDY_SPECIES\""
else
    SPECIES_JSON="null"
fi

cat > "$BUDDY_DIR/config.json" << CONF
{
  "name": "$BUDDY_NAME",
  "emoji": "$BUDDY_EMOJI",
  "species": $SPECIES_JSON,
  "memory_dir": $MEMORY_JSON,
  "memory_template": "# {date} Log\n\n## Summary\n",
  "memory_marker": "## Summary"
}
CONF

# Create initial stats if not exists
if [[ ! -f "$BUDDY_DIR/stats.json" ]]; then
    # Use official rolled personality stats as starting values
    if [[ -n "$DETECTED_JSON" ]]; then
        python3 -c "
import json, sys
detected = json.loads('$DETECTED_JSON')
stats = detected.get('stats', {})
initial = {
    'name': '$BUDDY_NAME',
    'level': 1,
    'totalExp': 0,
    'attributes': {
        'coding':   {'exp': 0, 'level': 1},
        'design':   {'exp': 0, 'level': 1},
        'research': {'exp': 0, 'level': 1},
        'devops':   {'exp': 0, 'level': 1},
        'writing':  {'exp': 0, 'level': 1}
    },
    'personality': {
        'debugging': stats.get('debugging', 50),
        'patience':  stats.get('patience', 50),
        'chaos':     stats.get('chaos', 50),
        'wisdom':    stats.get('wisdom', 50),
        'snark':     stats.get('snark', 50)
    },
    'titles': ['Baby $BUDDY_NAME'],
    'activeTitle': 'Baby $BUDDY_NAME',
    'unlocked': ['total_1'],
    'history': []
}
with open('$BUDDY_DIR/stats.json', 'w') as f:
    json.dump(initial, f, indent=2)
pers = initial['personality']
print(f'  ✓ Created initial stats with official personality:')
for k, v in pers.items():
    bar = '█' * (v // 10) + '░' * (10 - v // 10)
    print(f'    {k:10s} {bar} {v}')
"
    else
        cat > "$BUDDY_DIR/stats.json" << STATS
{
  "name": "$BUDDY_NAME",
  "level": 1,
  "totalExp": 0,
  "attributes": {
    "coding":   { "exp": 0, "level": 1 },
    "design":   { "exp": 0, "level": 1 },
    "research": { "exp": 0, "level": 1 },
    "devops":   { "exp": 0, "level": 1 },
    "writing":  { "exp": 0, "level": 1 }
  },
  "personality": {
    "debugging": 50, "patience": 50, "chaos": 50,
    "wisdom": 50, "snark": 50
  },
  "titles": ["Baby $BUDDY_NAME"],
  "activeTitle": "Baby $BUDDY_NAME",
  "unlocked": ["total_1"],
  "history": []
}
STATS
        echo "  ✓ Created initial stats (default personality)"
    fi
else
    echo "  ✓ Kept existing stats (not overwritten)"
fi

# Register hook in settings.json
if [[ -f "$SETTINGS" ]]; then
    # Check if hook already registered
    if grep -q "buddy-hook.sh" "$SETTINGS" 2>/dev/null; then
        echo "  ✓ Hook already registered"
    else
        # Add hook using python for safe JSON manipulation
        python3 -c "
import json
with open('$SETTINGS') as f:
    settings = json.load(f)
hooks = settings.setdefault('hooks', {})
stop = hooks.setdefault('Stop', [])
stop.append({'hooks': [{'type': 'command', 'command': '~/.claude/hooks/buddy-hook.sh'}]})
settings['statusLine'] = {'type': 'command', 'command': 'bash ~/.claude/buddy/statusline.sh'}
with open('$SETTINGS', 'w') as f:
    json.dump(settings, f, indent=2)
"
        echo "  ✓ Registered Stop hook"
        echo "  ✓ Configured statusline"
    fi
else
    echo "  ⚠ No settings.json found at $SETTINGS"
    echo "    You'll need to manually add the hook."
fi

# Install skill for /buddy command
SKILL_DIR="$HOME/.claude/skills/buddy-growth"
mkdir -p "$SKILL_DIR"
cat > "$SKILL_DIR/SKILL.md" << 'SKILL'
---
name: buddy
description: "Show buddy stats, interact with your buddy, or check achievements. Subcommands: /buddy (stats), /buddy feed, /buddy pet, /buddy battle, /buddy achievements, /buddy season. Use when user says /buddy or interacts with their companion."
user_invocable: true
---

# Buddy System

Read buddy's data from `~/.claude/buddy/`. Config in `config.json`, live state in `stats.json`, phrases in `phrases.json`, achievements in `achievements.json`, evolutions in `evolutions.json`.

## Subcommands

Parse the user's input to determine which subcommand:
- `/buddy` or `/buddy stats` → show full status card
- `/buddy feed` → feed interaction
- `/buddy pet` → pet interaction
- `/buddy battle` → compare stats
- `/buddy achievements` → show achievements
- `/buddy season` → show current season stats

## Status Card (`/buddy` or `/buddy stats`)

1. Read config.json, stats.json, phrases.json, evolutions.json
2. Display:
   - **Header**: name, emoji, level, active title, evolution stage, mood emoji
   - **Skill attributes**: All 5 bars (10 chars wide, █ filled ░ empty), progress = exp toward next level / (current_level * 50)
   - **Personality**: 🐛 Debugging, ⏳ Patience, 🌀 Chaos, 🧠 Wisdom, 🔥 Snark (0-100 bars)
   - **Mood**: Current mood with emoji and tone description
   - **Evolution**: Current stage name + description from evolutions.json, next stage conditions
   - **Achievements**: List unlocked ones with icons. Show "??? — Hidden" for locked hidden ones, show name for locked non-hidden ones
   - **Season**: Current month's total EXP, badges earned, dominant type
   - **Latest phrase**: from phrases.json using last unlocked key
   - **History**: last 5 entries newest first

## Feed (`/buddy feed`)

A fun interaction. Read stats.json, then:
1. Pick a random "food" based on dominant skill (coding→pizza, design→sushi, research→ramen, devops→energy drink, writing→tea)
2. Add +1 to a random personality stat (simulate nourishment)
3. Save stats.json
4. Print a cute message: "{emoji} {name} happily munches on {food}! (+1 {trait})"

## Pet (`/buddy pet`)

A fun interaction. Read stats.json, then:
1. Respond based on current mood: zen→purrs, hyper→bounces, sass→tolerates it, nerd→explains why petting releases oxytocin, grit→nods stoically, chill→leans in
2. Add +1 Patience, -1 Snark (petting calms them down)
3. Save stats.json
4. Print the response with emoji

## Battle (`/buddy battle`)

A fun comparison. Read stats.json, then:
1. Generate a random "opponent" buddy with random stats (use current timestamp as seed for reproducibility)
2. Compare each of the 5 personality stats
3. Whoever wins more stats wins the battle
4. Award a small bonus: +2 to the stat that won the most
5. Print a dramatic battle report with round-by-round comparison

## Achievements (`/buddy achievements`)

Read stats.json and achievements.json:
1. Show unlocked achievements with icon, name, and description
2. Show locked achievements: if hidden show "??? — Hidden achievement", if not hidden show name + description greyed out
3. Show progress: "X/Y achievements unlocked"

## Season (`/buddy season`)

Read stats.json seasons data for current month:
1. Show month name, total EXP, session count
2. Show breakdown by type with mini bar chart
3. Show badges earned this season
4. If previous seasons exist, show a comparison with last month
SKILL
echo "  ✓ Installed /buddy skill"

echo ""
echo "Done! $BUDDY_EMOJI $BUDDY_NAME is ready."
echo ""
echo "  • Statusline shows $BUDDY_NAME's level in real-time"
echo "  • Type /buddy to see full stats"
echo "  • $BUDDY_NAME gains EXP automatically from your tasks"
echo ""
echo "Restart Claude Code to activate."
