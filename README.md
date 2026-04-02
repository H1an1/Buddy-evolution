# Claude Buddy

An RPG-style upgrade system for your Claude Code companion. Your buddy gains EXP from your daily tasks, levels up attributes, and unlocks titles and phrases.

## Install

```bash
git clone https://github.com/user/claude-buddy.git
cd claude-buddy
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

## Attributes

| Attribute | What earns EXP |
|-----------|---------------|
| **Coding** | Bug fixes, feature dev, refactoring, debugging |
| **Design** | UI/UX work, Figma, mockups, visual design |
| **Research** | Investigation, docs, analysis, exploration |
| **DevOps** | Deployment, CI/CD, infrastructure, monitoring |
| **Writing** | Documentation, blog posts, specs, content |

## Leveling

- **Attribute levels**: Each level costs `current_level × 50` EXP
- **Total level**: Based on sum of all EXP, costs `current_level × 200`
- **EXP per task**: Small (5-10), Medium (15-25), Large (30-50)

## Commands

- **Statusline**: Always visible — shows buddy name, level, top 3 attributes
- **/buddy**: Full stats panel with progress bars, titles, and history

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
