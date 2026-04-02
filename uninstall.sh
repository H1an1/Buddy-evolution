#!/bin/bash
# Claude Buddy — Uninstall Script
set -e

echo "Removing Claude Buddy..."

# Remove files (keep stats.json as backup)
if [[ -f "$HOME/.claude/buddy/stats.json" ]]; then
    cp "$HOME/.claude/buddy/stats.json" "$HOME/.claude/buddy-stats-backup.json"
    echo "  ✓ Backed up stats to ~/.claude/buddy-stats-backup.json"
fi

rm -rf "$HOME/.claude/buddy"
rm -f "$HOME/.claude/hooks/buddy-hook.sh"
rm -rf "$HOME/.claude/skills/buddy-growth"

# Remove hook from settings.json
if [[ -f "$HOME/.claude/settings.json" ]]; then
    python3 -c "
import json
with open('$HOME/.claude/settings.json') as f:
    settings = json.load(f)
hooks = settings.get('hooks', {}).get('Stop', [])
settings['hooks']['Stop'] = [h for h in hooks if not any(
    hh.get('command', '').endswith('buddy-hook.sh')
    for hh in h.get('hooks', [])
)]
settings.pop('statusLine', None)
with open('$HOME/.claude/settings.json', 'w') as f:
    json.dump(settings, f, indent=2)
"
    echo "  ✓ Removed hook and statusline from settings"
fi

echo ""
echo "Done. Your buddy's stats were backed up to ~/.claude/buddy-stats-backup.json"
