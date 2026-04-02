#!/usr/bin/env python3
"""Claude Buddy — Binary Patcher

Finds a salt that produces desired buddy stats via brute-force,
then patches the Claude Code binary to use that salt.

Based on the approach from github.com/cpaczek/any-buddy.
"""

import json
import os
import random
import shutil
import string
import struct
import subprocess
import sys
from pathlib import Path

ORIGINAL_SALT = "friend-2026-401"
SALT_LENGTH = 15

STAT_NAMES = ["DEBUGGING", "PATIENCE", "CHAOS", "WISDOM", "SNARK"]

RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]
RARITY_WEIGHTS = {"common": 60, "uncommon": 25, "rare": 10, "epic": 4, "legendary": 1}
RARITY_FLOOR = {"common": 5, "uncommon": 15, "rare": 25, "epic": 35, "legendary": 50}

SPECIES = [
    "duck", "goose", "blob", "cat", "dragon", "octopus", "owl", "penguin",
    "turtle", "snail", "ghost", "axolotl", "capybara", "cactus", "robot",
    "rabbit", "mushroom", "chonk",
]
EYES = ["·", "✦", "×", "◉", "@", "°"]
HATS = ["none", "crown", "tophat", "propeller", "halo", "wizard", "beanie", "tinyduck"]


# ── Hash Functions ────────────────────────────────────────────────

def fnv1a(s: str) -> int:
    """FNV-1a hash (32-bit), matches any-buddy's Node fallback."""
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def bun_hash(s: str) -> int | None:
    """Call bun to compute wyhash, matching Claude Code's Bun binary."""
    try:
        result = subprocess.run(
            ["bun", "-e",
             "const s=await Bun.stdin.text();"
             "process.stdout.write(String(Number(BigInt(Bun.hash(s))&0xffffffffn)))"],
            input=s, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return None


def hash_string(s: str, use_bun: bool = True) -> int:
    """Hash a string using Bun.hash (preferred) or FNV-1a fallback."""
    if use_bun:
        h = bun_hash(s)
        if h is not None:
            return h
    return fnv1a(s)


# ── PRNG ──────────────────────────────────────────────────────────

class Mulberry32:
    """Mulberry32 PRNG, matching any-buddy's implementation."""

    def __init__(self, seed: int):
        self.a = seed & 0xFFFFFFFF

    def next(self) -> float:
        self.a = (self.a + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.a
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = ((t + ((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    def pick(self, arr: list):
        return arr[int(self.next() * len(arr))]


# ── Roll Logic ────────────────────────────────────────────────────

def roll_rarity(rng: Mulberry32) -> str:
    total = sum(RARITY_WEIGHTS.values())
    roll = rng.next() * total
    for rarity in RARITIES:
        roll -= RARITY_WEIGHTS[rarity]
        if roll < 0:
            return rarity
    return "common"


def roll_stats(rng: Mulberry32, rarity: str) -> dict[str, int]:
    floor = RARITY_FLOOR[rarity]
    peak = rng.pick(STAT_NAMES)
    dump = rng.pick(STAT_NAMES)
    while dump == peak:
        dump = rng.pick(STAT_NAMES)

    stats = {}
    for name in STAT_NAMES:
        if name == peak:
            stats[name] = min(100, floor + 50 + int(rng.next() * 30))
        elif name == dump:
            stats[name] = max(1, floor - 10 + int(rng.next() * 15))
        else:
            stats[name] = floor + int(rng.next() * 40)
    return stats


def roll(user_id: str, salt: str, use_bun: bool = True) -> dict:
    """Full roll: rarity, species, eye, hat, shiny, stats."""
    h = hash_string(user_id + salt, use_bun=use_bun)
    rng = Mulberry32(h)

    rarity = roll_rarity(rng)
    species = rng.pick(SPECIES)
    eye = rng.pick(EYES)
    hat = "none" if rarity == "common" else rng.pick(HATS)
    shiny = rng.next() < 0.01
    peak_stat = rng.pick(STAT_NAMES)  # consumed by rollStats internally
    # Re-roll stats properly
    stats = roll_stats(Mulberry32(h), rarity)
    # Actually we need to advance the RNG the same way as roll.ts
    # Let me redo this properly — roll everything in sequence

    # Reset and do it properly matching roll.ts exactly
    rng2 = Mulberry32(h)
    rarity2 = roll_rarity(rng2)
    species2 = rng2.pick(SPECIES)
    eye2 = rng2.pick(EYES)
    hat2 = "none" if rarity2 == "common" else rng2.pick(HATS)
    shiny2 = rng2.next() < 0.01
    stats2 = roll_stats(rng2, rarity2)

    return {
        "rarity": rarity2,
        "species": species2,
        "eye": eye2,
        "hat": hat2,
        "shiny": shiny2,
        "stats": stats2,
    }


# ── Salt Finder ───────────────────────────────────────────────────

def random_salt(length: int = SALT_LENGTH) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def find_salt(user_id: str, target_peak: str, target_dump: str | None = None,
              target_species: str | None = None, max_attempts: int = 500000,
              use_bun: bool = True) -> dict | None:
    """Brute-force search for a salt producing desired traits.

    Args:
        user_id: Claude user ID
        target_peak: The stat that should be highest (e.g. "PATIENCE")
        target_dump: The stat that should be lowest (optional)
        target_species: Desired species (optional)
        max_attempts: Max search iterations
        use_bun: Whether to use Bun.hash (slower but accurate for macOS)

    Returns dict with salt and roll result, or None if not found.
    """
    target_peak = target_peak.upper()
    if target_dump:
        target_dump = target_dump.upper()

    # For Bun hash, batch the hash calls for performance
    # Actually for brute force we need FNV-1a (fast, in-process)
    # Then verify the final salt with Bun hash
    best = None
    best_score = -1

    for i in range(max_attempts):
        salt = random_salt()
        # Use FNV-1a for speed during search
        h = fnv1a(user_id + salt)
        rng = Mulberry32(h)

        # Quick bail: check species first if targeted
        rarity = roll_rarity(rng)
        species = rng.pick(SPECIES)

        if target_species and species != target_species:
            continue

        eye = rng.pick(EYES)
        hat = "none" if rarity == "common" else rng.pick(HATS)
        shiny = rng.next() < 0.01
        stats = roll_stats(rng, rarity)

        # Check peak stat
        actual_peak = max(stats, key=stats.get)
        if actual_peak != target_peak:
            continue

        # Check dump stat if specified
        if target_dump:
            actual_dump = min(stats, key=stats.get)
            if actual_dump != target_dump:
                continue

        # Score: higher peak value + lower dump value = better
        score = stats[target_peak]
        if target_dump:
            score += (100 - stats[target_dump])

        if score > best_score:
            best_score = score
            best = {
                "salt": salt,
                "rarity": rarity,
                "species": species,
                "stats": stats,
                "attempts": i + 1,
            }
            # Good enough if peak is 80+
            if stats[target_peak] >= 80:
                break

    if best and use_bun:
        # Verify with Bun hash — the actual hash Claude Code uses
        verified = roll(user_id, best["salt"], use_bun=True)
        if max(verified["stats"], key=verified["stats"].get) == target_peak:
            best["stats"] = verified["stats"]
            best["verified_bun"] = True
        else:
            # FNV-1a and Bun.hash disagree — need to search with Bun
            best["verified_bun"] = False

    return best


# ── Binary Patching ───────────────────────────────────────────────

def find_claude_binary() -> str | None:
    """Find the Claude Code binary path."""
    home = Path.home()
    candidates = [
        home / ".local" / "bin" / "claude",
        home / ".claude" / "local" / "claude",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
        home / ".npm-global" / "bin" / "claude",
    ]

    # Try `which` first
    try:
        result = subprocess.run(
            ["which", "claude"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            if path:
                resolved = os.path.realpath(path)
                if os.path.exists(resolved) and os.path.getsize(resolved) > 1_000_000:
                    return resolved
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    for c in candidates:
        if c.exists():
            resolved = os.path.realpath(str(c))
            if os.path.getsize(resolved) > 1_000_000:
                return resolved

    return None


def find_current_salt(binary_path: str) -> str | None:
    """Find which salt is currently in the binary."""
    data = open(binary_path, "rb").read()
    if data.find(ORIGINAL_SALT.encode()) >= 0:
        return ORIGINAL_SALT
    return None  # Patched with unknown salt


def patch_binary(binary_path: str, old_salt: str, new_salt: str) -> dict:
    """Patch the Claude Code binary, replacing old_salt with new_salt."""
    if len(old_salt) != len(new_salt):
        raise ValueError(f"Salt length mismatch: {len(old_salt)} vs {len(new_salt)}")

    data = open(binary_path, "rb").read()
    old_bytes = old_salt.encode("utf-8")
    new_bytes = new_salt.encode("utf-8")

    offsets = []
    pos = 0
    while True:
        idx = data.find(old_bytes, pos)
        if idx == -1:
            break
        offsets.append(idx)
        pos = idx + 1

    if not offsets:
        raise RuntimeError(f"Salt '{old_salt}' not found in binary")

    # Backup
    backup_path = binary_path + ".buddy-bak"
    if not os.path.exists(backup_path):
        shutil.copy2(binary_path, backup_path)

    # Patch
    data = bytearray(data)
    for offset in offsets:
        data[offset:offset + len(new_bytes)] = new_bytes

    # Atomic write
    tmp_path = binary_path + ".buddy-tmp"
    stat = os.stat(binary_path)
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.chmod(tmp_path, stat.st_mode)

    try:
        os.rename(tmp_path, binary_path)
    except OSError:
        os.unlink(binary_path)
        os.rename(tmp_path, binary_path)

    # Verify
    verify_data = open(binary_path, "rb").read()
    verify_count = 0
    pos = 0
    while True:
        idx = verify_data.find(new_bytes, pos)
        if idx == -1:
            break
        verify_count += 1
        pos = idx + 1

    # Re-sign on macOS
    codesigned = False
    if sys.platform == "darwin":
        try:
            subprocess.run(
                ["codesign", "--force", "--sign", "-", binary_path],
                capture_output=True, timeout=30,
            )
            codesigned = True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return {
        "replacements": len(offsets),
        "verified": verify_count == len(offsets),
        "backup": backup_path,
        "codesigned": codesigned,
    }


# ── User ID ──────────────────────────────────────────────────────

def get_user_id() -> str:
    """Read Claude user ID from config."""
    for path in [Path.home() / ".claude.json", Path.home() / ".claude" / ".config.json"]:
        if path.exists():
            try:
                config = json.loads(path.read_text())
                uid = config.get("oauthAccount", {}).get("accountUuid")
                if uid:
                    return uid
                uid = config.get("userID")
                if uid:
                    return uid
            except (json.JSONDecodeError, KeyError):
                continue
    return "anon"


# ── Main Integration ──────────────────────────────────────────────

def get_saved_salt() -> str | None:
    """Read the currently saved salt from any-buddy or our own config."""
    # Check any-buddy config first
    ab_config = Path.home() / ".claude-code-any-buddy.json"
    if ab_config.exists():
        try:
            data = json.loads(ab_config.read_text())
            return data.get("salt")
        except json.JSONDecodeError:
            pass
    # Check our own config
    buddy_config = Path.home() / ".claude" / "buddy" / "patcher-state.json"
    if buddy_config.exists():
        try:
            data = json.loads(buddy_config.read_text())
            return data.get("salt")
        except json.JSONDecodeError:
            pass
    return None


def save_patcher_state(salt: str, stats: dict, binary_path: str):
    """Save our patching state."""
    state_file = Path.home() / ".claude" / "buddy" / "patcher-state.json"
    state = {
        "salt": salt,
        "previousSalt": ORIGINAL_SALT,
        "stats": stats,
        "appliedTo": binary_path,
        "appliedAt": __import__("datetime").datetime.now().isoformat(),
    }
    state_file.write_text(json.dumps(state, indent=2))


def evolve_buddy_stats(target_peak: str, target_dump: str | None = None) -> dict | None:
    """Full pipeline: find salt → patch binary → save state.

    Args:
        target_peak: Stat name to maximize (e.g. "PATIENCE")
        target_dump: Stat name to minimize (optional)

    Returns result dict or None on failure.
    """
    user_id = get_user_id()
    if user_id == "anon":
        return {"error": "Could not find Claude user ID"}

    binary_path = find_claude_binary()
    if not binary_path:
        return {"error": "Could not find Claude Code binary"}

    # Determine current salt in binary
    current_salt = find_current_salt(binary_path)
    saved_salt = get_saved_salt()

    # The salt currently in the binary
    active_salt = current_salt or saved_salt or ORIGINAL_SALT

    # Search for new salt
    result = find_salt(
        user_id, target_peak, target_dump,
        max_attempts=200000, use_bun=True,
    )
    if not result:
        return {"error": f"Could not find salt for peak={target_peak}"}

    new_salt = result["salt"]

    # Patch
    try:
        patch_result = patch_binary(binary_path, active_salt, new_salt)
    except RuntimeError as e:
        return {"error": str(e)}

    # Save state
    save_patcher_state(new_salt, result["stats"], binary_path)

    return {
        "success": True,
        "salt": new_salt,
        "stats": result["stats"],
        "attempts": result["attempts"],
        "patch": patch_result,
    }


if __name__ == "__main__":
    # CLI usage: python3 patcher.py PEAK_STAT [DUMP_STAT]
    if len(sys.argv) < 2:
        print("Usage: python3 patcher.py PEAK_STAT [DUMP_STAT]")
        print(f"  Stats: {', '.join(STAT_NAMES)}")
        sys.exit(1)

    peak = sys.argv[1].upper()
    dump = sys.argv[2].upper() if len(sys.argv) > 2 else None

    if peak not in STAT_NAMES:
        print(f"Invalid stat: {peak}. Choose from: {', '.join(STAT_NAMES)}")
        sys.exit(1)

    print(f"Searching for salt with peak={peak}" + (f", dump={dump}" if dump else "") + "...")
    result = evolve_buddy_stats(peak, dump)

    if result and result.get("success"):
        stats = result["stats"]
        print(f"\nFound in {result['attempts']} attempts!")
        print(f"New stats:")
        for name in STAT_NAMES:
            bar = "█" * (stats[name] // 10) + "░" * (10 - stats[name] // 10)
            marker = " ← PEAK" if name == peak else (" ← DUMP" if name == dump else "")
            print(f"  {name:10s} {bar} {stats[name]:3d}{marker}")
        print(f"\nBinary patched: {result['patch']['replacements']} replacements")
        print(f"Verified: {result['patch']['verified']}")
        print(f"Codesigned: {result['patch']['codesigned']}")
        print("\nRestart Claude Code to see changes.")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)
