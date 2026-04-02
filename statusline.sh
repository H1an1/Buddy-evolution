#!/bin/bash
# Claude Buddy — Statusline display
# Reads config.json + stats.json and outputs a colored one-liner

BUDDY_DIR="$HOME/.claude/buddy"
STATS_FILE="$BUDDY_DIR/stats.json"
CONFIG_FILE="$BUDDY_DIR/config.json"

# Drain stdin (Claude Code sends session JSON)
cat > /dev/null

[[ ! -f "$STATS_FILE" ]] && echo "Buddy — not initialized" && exit 0

python3 -c "
import json, sys

RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

ATTR_COLORS = {
    'coding':   '\033[32m',
    'design':   '\033[35m',
    'research': '\033[36m',
    'devops':   '\033[33m',
    'writing':  '\033[37m',
}

def level_style(level):
    if level >= 10: return BOLD
    if level >= 7:  return '\033[1m'
    return DIM if level < 3 else ''

def buddy_color(attrs):
    best = max(attrs.items(), key=lambda x: x[1]['exp'])
    return ATTR_COLORS.get(best[0], '')

try:
    stats = json.load(open('$STATS_FILE'))
except:
    print('Buddy — error')
    sys.exit(0)

try:
    config = json.load(open('$CONFIG_FILE'))
except:
    config = {}

name = config.get('name', stats.get('name', 'Buddy'))
emoji = config.get('emoji', '')
level = stats.get('level', 1)
title = stats.get('activeTitle', f'Baby {name}')
attrs = stats.get('attributes', {})
pc = buddy_color(attrs)

sorted_attrs = sorted(attrs.items(), key=lambda x: x[1]['exp'], reverse=True)
attr_parts = []
for aname, data in sorted_attrs[:3]:
    c = ATTR_COLORS.get(aname, '')
    s = level_style(data['level'])
    attr_parts.append(f'{s}{c}{aname.capitalize()} {data[\"level\"]}{RESET}')

attr_str = ' \u00b7 '.join(attr_parts)

# Personality — show the top trait
P_COLORS = {'debugging': '\033[31m', 'patience': '\033[34m', 'chaos': '\033[35m', 'wisdom': '\033[36m', 'snark': '\033[33m'}
P_EMOJI = {'debugging': '\U0001f41b', 'patience': '\u23f3', 'chaos': '\U0001f300', 'wisdom': '\U0001f9e0', 'snark': '\U0001f525'}
pers = stats.get('personality', {})
if pers:
    top_trait = max(pers, key=pers.get)
    top_val = pers[top_trait]
    tc = P_COLORS.get(top_trait, '')
    te = P_EMOJI.get(top_trait, '')
    trait_str = f' {tc}{te}{top_trait.capitalize()} {top_val}{RESET}'
else:
    trait_str = ''

# Mood
MOOD_EMOJI = {'zen': '\U0001f60c', 'hyper': '\u26a1', 'sass': '\U0001f485', 'nerd': '\U0001f913', 'grit': '\U0001f527', 'chill': '\U0001f60e'}
mood = stats.get('mood', 'chill')
mood_e = MOOD_EMOJI.get(mood, '')

print(f'{pc}{emoji} {name} Lv.{level}{RESET} {BOLD}\"{title}\"{RESET} {mood_e} \u2502 {attr_str}{trait_str}')
" 2>/dev/null || echo "Buddy"
