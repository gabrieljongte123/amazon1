"""Rainforest API integration for real Amazon product searches.

Uses the Rainforest API to search Amazon India for products. Aggressively caches
all responses to disk (JSON files) to minimize API usage. The API key has a 100-search
limit, so we cache everything and serve from cache whenever possible.

Cache strategy:
- Each unique search term gets cached to backend/data/cache/{normalized_term}.json
- Cache never expires (since API access will be lost after hackathon)
- Max 3 products cached per search to keep responses fast
"""

import json
import hashlib
import logging
import os
from pathlib import Path
from typing import Any

import requests

from config import settings

logger = logging.getLogger(__name__)

# API Configuration
RAINFOREST_API_KEY = os.getenv("RAINFOREST_API_KEY", "66A90651323A4814AC4439ED4BC2ED1E")
RAINFOREST_BASE_URL = "https://api.rainforestapi.com/request"
AMAZON_DOMAIN = "amazon.in"  # Amazon India

# Cache directory
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Max products to cache per search term
MAX_CACHED_PRODUCTS = 3


def _get_cache_path(search_term: str) -> Path:
    """Get the cache file path for a search term."""
    # Use a hash for safe filenames
    safe_name = hashlib.md5(search_term.lower().strip().encode()).hexdigest()
    return CACHE_DIR / f"{safe_name}.json"


def _read_cache(search_term: str) -> list[dict] | None:
    """Read cached results for a search term. Returns None if not cached."""
    cache_path = _get_cache_path(search_term)
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Cache HIT for '{search_term}' ({len(data.get('products', []))} products)")
                return data.get("products", [])
        except (json.JSONDecodeError, IOError):
            return None
    return None


def _write_cache(search_term: str, products: list[dict]) -> None:
    """Write search results to cache."""
    cache_path = _get_cache_path(search_term)
    data = {
        "searchTerm": search_term,
        "products": products[:MAX_CACHED_PRODUCTS],
        "source": "rainforest_api",
        "domain": AMAZON_DOMAIN,
    }
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Cached {len(products[:MAX_CACHED_PRODUCTS])} products for '{search_term}'")
    except IOError as e:
        logger.error(f"Failed to write cache for '{search_term}': {e}")


def _parse_search_results(api_response: dict) -> list[dict]:
    """Parse Rainforest API search results into our product format."""
    products = []
    search_results = api_response.get("search_results", [])

    for item in search_results[:MAX_CACHED_PRODUCTS]:
        product = {
            "productId": item.get("asin", ""),
            "title": item.get("title", "Unknown Product"),
            "brand": item.get("brand", item.get("manufacturer", "")),
            "price": _extract_price(item),
            "rating": item.get("rating", 0.0),
            "imageUrl": item.get("image", "https://via.placeholder.com/300x300/f5f5f5/232f3e?text=Product"),
            "url": item.get("link", ""),
            "isPrime": item.get("is_prime", False),
            "reviewCount": item.get("ratings_total", 0),
        }
        if product["price"] > 0:  # Only include products with valid prices
            products.append(product)

    return products


def _extract_price(item: dict) -> float:
    """Extract price from a Rainforest API search result item."""
    # Try price.value first
    price_data = item.get("price", {})
    if isinstance(price_data, dict):
        value = price_data.get("value")
        if value:
            return float(value)
        # Try raw string
        raw = price_data.get("raw", "")
        if raw:
            # Extract number from strings like "₹2,799.00"
            import re
            match = re.search(r"[\d,]+\.?\d*", raw.replace(",", ""))
            if match:
                return float(match.group())

    # Try prices array
    prices = item.get("prices", [])
    if prices and isinstance(prices, list):
        for p in prices:
            if isinstance(p, dict) and p.get("value"):
                return float(p["value"])

    return 0.0


def search_products(search_term: str, max_results: int = 3) -> list[dict]:
    """Search for products using cached Rainforest API results.

    STRICT matching only:
    1. Exact cache match on the full search term
    2. Exact cache match on close variations (plural/singular)
    
    Does NOT do word-by-word matching (causes "iphones"→"headphones" bugs).
    The caller (product_catalog.search_and_recommend) handles similar matching.

    Args:
        search_term: The product to search for (e.g., "puma sneakers")
        max_results: Maximum products to return (default 3)

    Returns:
        List of product dicts. Empty list if not found in cache.
    """
    normalized = search_term.lower().strip()

    # 1. Exact cache match
    cached = _read_cache(normalized)
    if cached is not None:
        return cached[:max_results]

    # 2. Try common variations (plural/singular, with/without 's')
    variations = []
    if normalized.endswith("s"):
        variations.append(normalized[:-1])  # "iphones" → "iphone"
    else:
        variations.append(normalized + "s")  # "iphone" → "iphones"
    
    if normalized.endswith("es"):
        variations.append(normalized[:-2])  # "watches" → "watch"
    
    # Try with/without common prefixes
    for prefix in ["i want ", "i need ", "get me "]:
        if normalized.startswith(prefix):
            variations.append(normalized[len(prefix):])
    
    for var in variations:
        cached = _read_cache(var)
        if cached is not None:
            return cached[:max_results]

    # 3. For multi-word queries, try the full phrase in different orders
    words = normalized.split()
    if len(words) >= 2:
        # Try "word2 word1" (e.g., "baby oil" → "oil baby" — unlikely to help but safe)
        # More useful: try without filler words
        content_words = [w for w in words if w not in ("i", "a", "the", "want", "need", "some", "get", "me", "for")]
        if content_words and " ".join(content_words) != normalized:
            cached = _read_cache(" ".join(content_words))
            if cached is not None:
                return cached[:max_results]

    # 4. Return empty — let the caller handle fallback
    return []


def get_cached_terms() -> list[str]:
    """Get all search terms that have been cached."""
    terms = []
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                terms.append(data.get("searchTerm", ""))
        except (json.JSONDecodeError, IOError):
            pass
    return [t for t in terms if t]


def get_cache_stats() -> dict:
    """Get cache statistics."""
    cache_files = list(CACHE_DIR.glob("*.json"))
    total_products = 0
    for f in cache_files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                total_products += len(data.get("products", []))
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "cached_searches": len(cache_files),
        "total_products": total_products,
        "cache_dir": str(CACHE_DIR),
    }
