#!/bin/bash
# Claude Buddy — Stop hook
# Reads conversation transcript path from stdin, passes to update.py

BUDDY_DIR="$HOME/.claude/buddy"
UPDATE_SCRIPT="$BUDDY_DIR/update.py"

[[ ! -f "$UPDATE_SCRIPT" ]] && exit 0

HOOK_INPUT=$(cat)

TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    print(data.get('transcript_path', ''))
except:
    print('')
" 2>/dev/null)

[[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]] && exit 0

python3 "$UPDATE_SCRIPT" "$TRANSCRIPT_PATH" &

exit 0
