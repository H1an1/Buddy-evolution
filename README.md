# Claude Buddy

An RPG-style upgrade system for your Claude Code companion. Your buddy grows in two dimensions: **skill attributes** from the type of work you do, and **personality traits** from how you work.

## Install

```bash
git clone https://github.com/H1an1/Buddy-evolution.git
cd Buddy-evolution
./install.sh
```

The installer will ask you to:
1. **Name your buddy** (default: "Buddy")
2. **Pick an emoji** (default: 🤖)
3. **Set a memory directory** (optional — for daily log integration)

Then restart Claude Code.

## How It Works

```
You use Claude Code normally
         ↓
After each response, a Stop hook fires
         ↓
Analyzes conversation → classifies task type
         ↓
Awards EXP to matching attribute
         ↓
Checks for level-ups and title unlocks
         ↓
Statusline updates in real-time
```

## Skill Attributes

Classified each turn by keyword matching. Determines **what** you're working on.

| Attribute | What earns EXP |
|-----------|---------------|
| **Coding** | Bug fixes, feature dev, refactoring, debugging |
| **Design** | UI/UX work, Figma, mockups, visual design |
| **Research** | Investigation, docs, analysis, exploration |
| **DevOps** | Deployment, CI/CD, infrastructure, monitoring |
| **Writing** | Documentation, blog posts, specs, content |

## Personality Traits

Analyzed once per session from behavioral signals. Determines **how** you work.

| Trait | Range | Goes up when... | Goes down when... |
|-------|-------|----------------|-------------------|
| 🐛 **Debugging** | 0–100 | Errors → retries → success, heavy Bash usage | Only running commands, never writing code |
| ⏳ **Patience** | 0–100 | Long sessions (2h+), late night work, high message count | — |
| 🌀 **Chaos** | 0–100 | Project-hopping, many tool types, parallel Agents | — |
| 🧠 **Wisdom** | 0–100 | Reading more than writing, using WebSearch | — |
| 🔥 **Snark** | 0–100 | Days of absence (buddy gets snarky), very short sessions | Daily usage (buddy calms down) |

## Leveling

- **Attribute levels**: Each level costs `current_level × 50` EXP
- **Total level**: Based on sum of all EXP, costs `current_level × 200`
- **EXP per task**: Small (5–10), Medium (15–25), Large (30–50)
- **Personality**: Starts at 50, drifts based on your behavior over time

## Commands

- **Statusline**: Always visible — shows level, top 3 skills, and dominant personality trait
- **/growth**: Full stats panel with progress bars, personality, titles, and history
- **/growth feed**: Feed your buddy (+1 random personality stat)
- **/growth pet**: Pet your buddy (+1 Patience, -1 Snark)
- **/growth battle**: Battle a random opponent
- **/growth achievements**: View unlocked and hidden achievements
- **/growth season**: Monthly stats and badges

## Customization

Edit `~/.claude/buddy/config.json`:

```json
{
  "name": "Pickle",
  "emoji": "🥒",
  "memory_dir": "~/Documents/my-notes/daily/",
  "memory_template": "# {date} Log\n\n## Summary\n",
  "memory_marker": "## Summary"
}
```

Edit `~/.claude/buddy/titles.json` and `~/.claude/buddy/phrases.json` to customize titles and unlock phrases. Use `{name}` as a placeholder for the buddy's name.

## Uninstall

```bash
./uninstall.sh
```

Stats are backed up to `~/.claude/buddy-stats-backup.json`.

## File Structure

```
~/.claude/buddy/
├── config.json       # Name, emoji, memory settings
├── stats.json        # Live state (levels, EXP, history)
├── titles.json       # Title definitions per level
├── phrases.json      # Unlock phrases per milestone
├── update.py         # Core engine
└── statusline.sh     # Statusline display script

~/.claude/hooks/
└── buddy-hook.sh     # Stop hook entry point

~/.claude/skills/buddy-status/
└── SKILL.md          # /buddy slash command
```

## License

MIT
