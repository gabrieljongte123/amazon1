"""Fix cache: remove all empty cached results so they can be re-fetched."""
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "data" / "cache"

removed = 0
kept = 0

for f in CACHE_DIR.glob("*.json"):
    try:
        data = json.load(open(f, "r", encoding="utf-8"))
        if not data.get("products"):
            f.unlink()
            removed += 1
            print(f"  REMOVED (empty): {data.get('searchTerm', 'unknown')}")
        else:
            kept += 1
    except Exception:
        f.unlink()
        removed += 1

print(f"\nRemoved {removed} empty caches, kept {kept} valid caches.")
