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

cat > "$BUDDY_DIR/config.json" << CONF
{
  "name": "$BUDDY_NAME",
  "emoji": "$BUDDY_EMOJI",
  "memory_dir": $MEMORY_JSON,
  "memory_template": "# {date} Log\n\n## Summary\n",
  "memory_marker": "## Summary"
}
CONF

# Create initial stats if not exists
if [[ ! -f "$BUDDY_DIR/stats.json" ]]; then
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
  "titles": ["Baby $BUDDY_NAME"],
  "activeTitle": "Baby $BUDDY_NAME",
  "unlocked": ["total_1"],
  "history": []
}
STATS
    echo "  ✓ Created initial stats (Lv.1 Baby $BUDDY_NAME)"
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
