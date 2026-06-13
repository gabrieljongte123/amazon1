"""Pre-cache brand+product combinations from Rainforest API v2.

Covers popular brands for each product type so every brand shows results.
Uses the new API key. Budget: ~90 searches.
"""

import time
import json
from services.rainforest_api import search_products, get_cache_stats, _read_cache

# Brand + Product combinations to pre-cache
SEARCHES = [
    # Sneakers - all brands
    "puma sneakers", "nike sneakers", "adidas sneakers", "converse sneakers",
    "reebok sneakers", "new balance sneakers", "skechers sneakers",
    # Shoes - brands
    "nike shoes", "adidas shoes", "puma shoes", "woodland shoes", "bata shoes",
    "red tape shoes", "sparx shoes",
    # Jeans - brands
    "levis jeans", "wrangler jeans", "pepe jeans", "spykar jeans", "lee jeans",
    # T-shirts
    "nike t shirt", "adidas t shirt", "puma t shirt", "us polo t shirt",
    # Watches
    "titan watch", "fastrack watch", "casio watch", "fossil watch",
    # Earbuds - brands
    "boat earbuds", "noise earbuds", "sony earbuds", "jbl earbuds", "samsung earbuds",
    # Headphones
    "sony headphones", "jbl headphones", "boat headphones", "sennheiser headphones",
    # Laptops
    "hp laptop", "dell laptop", "lenovo laptop", "asus laptop", "acer laptop",
    # Phones
    "samsung phone", "oneplus phone", "xiaomi phone", "realme phone", "iphone",
    # Smartwatch
    "noise smartwatch", "boat smartwatch", "fire boltt smartwatch", "apple watch",
    # Dumbbells
    "kore dumbbells", "protoner dumbbells", "decathlon dumbbells",
    # Protein
    "muscleblaze protein", "optimum nutrition protein", "myprotein whey",
    # Home
    "prestige pressure cooker", "hawkins pressure cooker", "milton water bottle",
    # Baby
    "pampers diapers", "huggies diapers", "mamypoko diapers",
    # Beauty
    "maybelline lipstick", "lakme lipstick", "mamaearth face wash", "himalaya face wash",
    # Specific popular items
    "adidas superstar", "nike air force 1", "converse chuck taylor",
    "boat airdopes", "noise buds", "jbl tune",
    "samsung galaxy", "oneplus nord", "redmi note",
    # Colors + products
    "black sneakers", "white sneakers", "black shoes men",
    "blue jeans men", "black jeans",
]

def main():
    print(f"Pre-caching {len(SEARCHES)} brand+product searches...")
    print(f"Current cache: {get_cache_stats()}")
    print()

    cached = 0
    skipped = 0
    failed = 0

    for i, term in enumerate(SEARCHES, 1):
        if _read_cache(term) is not None:
            print(f"  [{i}/{len(SEARCHES)}] CACHED: {term}")
            skipped += 1
            continue

        print(f"  [{i}/{len(SEARCHES)}] Fetching: {term}...", end=" ", flush=True)
        results = search_products(term)

        if results:
            print(f"OK ({len(results)} products)")
            cached += 1
        else:
            print("EMPTY/ERROR")
            failed += 1

        time.sleep(1)

    print()
    print(f"Done! Cached: {cached}, Skipped: {skipped}, Failed: {failed}")
    print(f"Total API credits used this run: {cached}")
    print(f"Final cache stats: {get_cache_stats()}")


if __name__ == "__main__":
    main()
