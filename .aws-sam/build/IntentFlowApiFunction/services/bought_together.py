"""Frequently Bought Together service.

Provides product pairing recommendations based on what customers commonly buy together.
Uses a local JSON database of product pairs.
"""

import json
from pathlib import Path
from difflib import SequenceMatcher

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "bought_together.json"
_pairs: dict[str, list[str]] = {}


def _load_pairs():
    """Load bought-together pairs from JSON."""
    global _pairs
    if _DATA_PATH.exists():
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            _pairs = data.get("pairs", {})

_load_pairs()


def get_bought_together(product_query: str) -> list[str]:
    """Get frequently bought together suggestions for a product.
    
    Args:
        product_query: The product name/search term (e.g., "pliers", "yoga mat")
    
    Returns:
        List of product names commonly bought with this item.
    """
    query_lower = product_query.lower().strip()
    
    # 1. Exact match
    if query_lower in _pairs:
        return _pairs[query_lower]
    
    # 2. Check if query contains a key or vice versa
    for key, suggestions in _pairs.items():
        if key in query_lower or query_lower in key:
            return suggestions
    
    # 3. Word-level matching
    query_words = set(query_lower.split())
    for key, suggestions in _pairs.items():
        key_words = set(key.split())
        if query_words & key_words:  # shared words
            return suggestions
    
    # 4. Fuzzy match
    best_match = None
    best_score = 0.0
    for key in _pairs:
        score = SequenceMatcher(None, query_lower, key).ratio()
        if score > best_score and score >= 0.7:
            best_score = score
            best_match = key
    
    if best_match:
        return _pairs[best_match]
    
    return []
