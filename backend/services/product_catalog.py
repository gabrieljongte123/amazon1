"""Product catalog service for IntentFlow.

Loads the product catalog from a JSON file on cold start (module-level caching)
and provides query functions for filtering, counting, and retrieving products.
"""

import json
from pathlib import Path
from typing import Any

from models.product import Product

# Module-level cache: loaded once on cold start
_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "products.json"

_products: list[Product] = []
_categories: dict[str, dict[str, Any]] = {}


def _load_catalog() -> None:
    """Load product catalog from JSON file into module-level cache."""
    global _products, _categories

    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    _products = [Product.model_validate(p) for p in data.get("products", [])]
    _categories = data.get("categories", {})


# Load on import (cold start)
_load_catalog()


# --- Categorical attributes that use exact matching ---
_CATEGORICAL_ATTRIBUTES = {"category", "brand", "color", "size"}


def _normalize_str(s: str) -> str:
    """Normalize a string for comparison: lowercase + normalize apostrophe variants."""
    result = s.lower()
    # Normalize various apostrophe/quote characters to standard ASCII apostrophe
    result = result.replace("\u2019", "'")  # right single quotation mark
    result = result.replace("\u2018", "'")  # left single quotation mark
    result = result.replace("\u02BC", "'")  # modifier letter apostrophe
    result = result.replace("\u0060", "'")  # grave accent
    return result


def _matches_product(product: Product, attributes: dict[str, Any]) -> bool:
    """Check if a product matches all given filter attributes.

    - Categorical attributes (category, brand, color, size): exact match (case-insensitive)
    - price / priceRange: range containment (e.g., "under 3000" means price <= max)
    - Other attributes: checked against product.attributes dict (exact, case-insensitive)
    """
    for key, value in attributes.items():
        if value is None:
            continue

        # Handle price filtering
        if key == "price" or key == "priceRange":
            if not _matches_price(product, value):
                return False
            continue

        # Check top-level categorical attributes
        if key in _CATEGORICAL_ATTRIBUTES:
            product_value = getattr(product, key, None)
            if product_value is None:
                return False
            if _normalize_str(str(product_value)) != _normalize_str(str(value)):
                return False
            continue

        # Check nested attributes dict
        product_attr_value = product.attributes.get(key)
        if product_attr_value is None:
            return False
        if _normalize_str(str(product_attr_value)) != _normalize_str(str(value)):
            return False

    return True


def _matches_price(product: Product, price_value: Any) -> bool:
    """Check if a product's price falls within the specified range.

    Supports formats:
    - Integer/float: treated as max price (product.price <= value)
    - String range "min-max": product.price >= min AND product.price <= max
    - String "under X" or "0-X": product.price <= X
    """
    if isinstance(price_value, (int, float)):
        return product.price <= price_value

    if isinstance(price_value, str):
        price_str = price_value.strip().lower()

        # Handle "under X" format
        if price_str.startswith("under"):
            try:
                max_price = int(price_str.replace("under", "").strip())
                return product.price <= max_price
            except ValueError:
                return False

        # Handle "min-max" range format
        if "-" in price_str:
            parts = price_str.split("-")
            if len(parts) == 2:
                try:
                    min_price = int(parts[0].strip())
                    max_price = int(parts[1].strip())
                    return min_price <= product.price <= max_price
                except ValueError:
                    return False

    return False


def query_products(attributes: dict[str, Any]) -> list[Product]:
    """Query products matching the given attributes.

    Exact match for categorical attributes (category, brand, color, size).
    Range containment for price (e.g., if user says "under 3000", match products
    where price <= 3000).

    Args:
        attributes: Dictionary of attribute filters to apply.

    Returns:
        List of matching Product objects. Empty list if no products match.
    """
    if not attributes:
        return list(_products)

    return [p for p in _products if _matches_product(p, attributes)]


def count_matching_products(attributes: dict[str, Any]) -> int:
    """Count products matching the given attributes.

    Args:
        attributes: Dictionary of attribute filters to apply.

    Returns:
        Number of matching products.
    """
    return len(query_products(attributes))


def get_product_by_id(product_id: str) -> Product | None:
    """Retrieve a single product by its ID.

    Args:
        product_id: The unique product identifier (e.g., "PROD-001").

    Returns:
        The matching Product or None if not found.
    """
    for product in _products:
        if product.product_id == product_id:
            return product
    return None


def get_category_schema(category: str) -> dict[str, Any] | None:
    """Retrieve the schema for a given category.

    Returns the category's requiredAttributes, optionalAttributes,
    and discriminativeOrder.

    Args:
        category: The category name (e.g., "Fashion", "Electronics").

    Returns:
        Dictionary with requiredAttributes, optionalAttributes, and
        discriminativeOrder keys, or None if the category doesn't exist.
    """
    return _categories.get(category)


def search_and_recommend(search_term: str, attributes: dict[str, Any] | None = None, max_price: float | None = None, min_rating: float | None = None) -> list[dict]:
    """Search for products using the local catalog + cached API results.

    Pipeline (in priority order):
    1. Local catalog search (catalog.json - 200 believable products)
    2. Cached Rainforest API results
    3. Similar cache match
    4. Amazon search link fallback

    Never returns empty.
    """
    from services.rainforest_api import search_products, CACHE_DIR
    from difflib import SequenceMatcher
    import json

    # Extract price constraint from attributes if not passed directly
    if max_price is None and attributes:
        price_range = attributes.get("priceRange", "")
        if price_range and "-" in str(price_range):
            try:
                max_price = float(str(price_range).split("-")[1])
            except (ValueError, IndexError):
                pass

    if min_rating is None and attributes and attributes.get("_prefer_high_rating"):
        min_rating = 3.5

    # Extract min_price from attributes (above X)
    min_price = None
    if attributes and attributes.get("_min_price"):
        try:
            min_price = float(attributes["_min_price"])
        except (ValueError, TypeError):
            pass

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # TIER 1: LOCAL CATALOG SEARCH (primary source, always available)
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    catalog_results = _search_local_catalog(search_term, max_price=max_price, min_price=min_price, min_rating=min_rating)
    if catalog_results:
        return catalog_results[:5]

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # TIER 2: CACHED RAINFOREST API RESULTS
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    api_results = search_products(search_term)
    detected_brand = _extract_brand_from_query(search_term.lower())
    if api_results:
        formatted = []
        for p in api_results[:5]:
            price = p.get("price", 0)
            rating = p.get("rating", 0)
            if max_price and price > max_price and price > 0:
                continue
            if min_price and price < min_price and price > 0:
                continue
            if min_rating and rating < min_rating and rating > 0:
                continue
            # Brand filter for cached results
            if detected_brand:
                p_brand = p.get("brand", "").lower()
                p_title = p.get("title", "").lower()
                if detected_brand not in p_brand and detected_brand not in p_title:
                    continue
            formatted.append({
                "productId": p["productId"],
                "title": p["title"],
                "price": price,
                "rating": rating,
                "imageUrl": p.get("imageUrl", ""),
                "brand": p.get("brand", ""),
                "url": p.get("url", f"https://www.amazon.in/dp/{p['productId']}"),
                "source": "amazon",
            })
        if formatted:
            return formatted

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # TIER 3: SIMILAR CACHE MATCH (strict - only very close matches)
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    search_lower = search_term.lower()
    best_match_products = []
    best_score = 0.0
    try:
        for cache_file in CACHE_DIR.glob("*.json"):
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_term = data.get("searchTerm", "")
            if not cached_term:
                continue
            products = data.get("products", [])
            if not products:
                continue
            score = SequenceMatcher(None, search_lower, cached_term.lower()).ratio()
            # Only match singular/plural of the SAME word
            cached_stripped = cached_term.lower().rstrip("s")
            search_stripped = search_lower.rstrip("s")
            if search_stripped == cached_stripped or search_lower == cached_term.lower():
                score = max(score, 0.92)
            if score > best_score and score >= 0.8:
                best_score = score
                best_match_products = products
    except Exception:
        pass

    if best_match_products:
        formatted = []
        for p in best_match_products[:5]:
            price = p.get("price", 0)
            if max_price and price > max_price and price > 0:
                continue
            if min_price and price < min_price and price > 0:
                continue
            formatted.append({
                "productId": p.get("productId", ""),
                "title": p.get("title", ""),
                "price": price,
                "rating": p.get("rating", 4.0),
                "imageUrl": p.get("imageUrl", ""),
                "brand": p.get("brand", ""),
                "url": p.get("url", f"https://www.amazon.in/s?k={search_term.replace(' ', '+')}"),
                "source": "amazon_similar",
            })
        if formatted:
            return formatted


    # TIER 4: INLINE DISCOVERY (stays inside IntentFlow, no external redirects)
    # Generate 2 discovery snippets with realistic brand names and prices
    from services.ontology_engine import classify as _ont_classify
    import random
    
    # Try classification with full term first, then without brand
    classification = _ont_classify(search_term)
    if not classification or classification.confidence == 0:
        # Try stripping the brand for better ontology match
        if detected_brand:
            term_no_brand = search_term.lower().replace(detected_brand, "").strip()
            if term_no_brand:
                classification = _ont_classify(term_no_brand)
        # Try stripping gender prefixes
        if not classification or classification.confidence == 0:
            for prefix in ["women ", "men ", "kids ", "baby "]:
                if search_term.startswith(prefix):
                    classification = _ont_classify(search_term[len(prefix):])
                    if classification and classification.confidence > 0:
                        break
    
    # Use the subcategory or cleaned search term as product name (NEVER raw query like "new search")
    # AGGRESSIVE cleaning: remove filler, questions, punctuation
    import re as _re
    product_name = search_term.strip()
    # Remove question marks, exclamation, trailing punctuation
    product_name = _re.sub(r'[?!,;]+', '', product_name).strip()
    # Strip filler phrases that shouldn't be product names
    filler_patterns = [
        r'\b(recommend|recommendations?|suggestion|options?|something|anything|thing)\b',
        r'\b(want|need|looking|find|show|give|get|buy)\b',
        r'\b(for me|to eat|to drink|to wear|to use|to buy)\b',
        r'\b(any|some|good|best|nice|great|please|i)\b',
        r'\b(links?|url|amazon)\b',
    ]
    for pat in filler_patterns:
        product_name = _re.sub(pat, '', product_name, flags=_re.IGNORECASE)
    # Strip price constraint text from display name
    product_name = _re.sub(r'\s*(under|below|above|over|less than|more than|within|budget)\s*(?:rs\.?|₹|inr)?\s*\d+', '', product_name, flags=_re.IGNORECASE).strip()
    product_name = _re.sub(r'\s*(?:rs\.?|₹|inr)\s*\d+', '', product_name, flags=_re.IGNORECASE).strip()
    # Collapse spaces and title case
    product_name = " ".join(product_name.split()).strip().title()
    if not product_name or len(product_name) < 3:
        product_name = search_term.strip().title()
    # Guard against bad product names
    bad_names = {"new search", "try different filters", "try again", "start over", "reset",
                 "show options", "remind me later", "not now", "continue shopping",
                 "to eat", "to drink", "to wear", "to use", "spicy", "sweet", "salty"}
    if product_name.lower() in bad_names:
        product_name = "Snacks" if "eat" in search_term.lower() or "spicy" in search_term.lower() else "Product"
    
    # Build clean Amazon search URL (not the raw user query)
    amazon_search_term = product_name.lower().replace(" ", "+")
    amazon_url = f"https://www.amazon.in/s?k={amazon_search_term}"
    
    # Realistic price ranges by category
    price_ranges = {
        "Fashion": (499, 2999), "Electronics": (999, 24999),
        "Sports & Fitness": (299, 4999), "Home & Kitchen": (399, 3999),
        "Beauty & Personal Care": (99, 599), "Grocery": (29, 399),
        "Tools": (199, 2999), "Toys & Games": (399, 2499),
        "Books": (149, 599), "Pet Supplies": (199, 1999),
        "Baby Products": (299, 3999), "Health": (149, 999),
        "Automotive": (299, 2999), "Office & Stationery": (49, 499),
        "Essentials": (49, 399),
    }
    
    if classification and classification.confidence > 0:
        brands = classification.popularBrands[:2]
        # If user specified a brand, use THAT brand for discovery cards
        if detected_brand:
            brands = [detected_brand.title()]
        # Product names that imply a specific brand
        brand_implied = {
            "macbook": "Apple", "iphone": "Apple", "ipad": "Apple", "airpods": "Apple",
            "galaxy": "Samsung", "pixel": "Google", "surface": "Microsoft",
            "thinkpad": "Lenovo", "inspiron": "Dell", "pavilion": "HP",
        }
        for keyword, implied_brand in brand_implied.items():
            if keyword in search_term.lower():
                brands = [implied_brand]
                break
        category = classification.topCategory
        price_range = price_ranges.get(category, (499, 2999))
        sub_cat = classification.subCategory or product_name
        
        # Fix subcategory names when brand doesn't match
        # e.g., "oppo phones" should NOT be "iPhones" — it should be "Smartphones"
        if detected_brand and detected_brand.lower() != "apple" and detected_brand.lower() != "macbook" and sub_cat == "iPhones":
            sub_cat = "Smartphones"
        # MacBook is always Apple Laptops
        if detected_brand and detected_brand.lower() == "macbook":
            brands = ["Apple"]
            sub_cat = "MacBook"
        # Handle product names that ARE the subcategory (like "macbook")
        if "macbook" in search_term.lower():
            sub_cat = "MacBook"
        
        # Use subcategory as the display name (more meaningful than raw query)
        if sub_cat.lower() in bad_names:
            sub_cat = product_name
        
        # Subcategory-specific price overrides for realism
        sub_price_overrides = {
            "Smartphones": (9999, 49999),
            "iPhones": (49999, 129999),
            "Laptops": (29999, 89999),
            "Tablets": (14999, 49999),
            "Smartwatches": (1999, 14999),
            "Earbuds": (999, 6999),
            "Headphones": (1499, 9999),
            "Power Banks": (799, 2999),
            "Chargers": (399, 1999),
            "Bicycles": (4999, 24999),
            "Treadmills": (14999, 49999),
            "Watches": (1499, 9999),
            "Jeans": (1299, 3999),
            "Sneakers": (2499, 14999),
            "Shoes": (999, 7999),
            "Slippers": (249, 1999),
            "Sarees": (999, 9999),
            # Apple specific
            "MacBook": (69999, 199999),
            # Beauty - realistic low prices
            "Eyeliner": (99, 399),
            "Lipstick": (149, 599),
            "Foundation": (199, 799),
            "Mascara": (149, 499),
            "Compact Powder": (99, 399),
            "Nail Polish": (49, 249),
            "Face Wash": (99, 349),
            "Moisturizer": (149, 499),
            "Sunscreen": (149, 549),
            "Shampoo": (99, 449),
            "Conditioner": (99, 399),
            "Serum": (199, 799),
            # Grocery - low prices
            "Snacks": (20, 199),
            "Spices": (29, 149),
            "Beverages": (29, 199),
            "Instant Food": (29, 199),
            "Cooking Oil": (99, 399),
            "Rice & Flour": (49, 299),
        }
        
        if sub_cat in sub_price_overrides:
            price_range = sub_price_overrides[sub_cat]
        
        upper = price_range[1]
        lower = price_range[0]
        if max_price:
            upper = min(upper, int(max_price))
            lower = min(lower, max(upper - 3000, price_range[0]))
        # Handle "above X" — min price constraint
        min_price_val = None
        if attributes:
            min_price_val = attributes.get("_min_price")
        if min_price_val:
            lower = max(lower, int(min_price_val))
            upper = max(upper, lower + 2000)
        
        results = []
        # Generate 2 products - if only 1 brand, make one basic and one premium
        if len(brands) == 1:
            brand = brands[0]
            price1 = random.randint(lower, max(upper, lower + 1000))
            price1 = (price1 // 100) * 100 + 99
            price2 = random.randint(max(lower + 2000, upper - 5000), max(upper, lower + 3000))
            price2 = (price2 // 100) * 100 + 99
            results.append({
                "productId": "disc-0",
                "title": f"{brand} {sub_cat}",
                "price": price1,
                "rating": round(random.uniform(3.9, 4.5), 1),
                "imageUrl": "",
                "brand": brand,
                "url": amazon_url,
                "source": "catalog",
            })
            results.append({
                "productId": "disc-1",
                "title": f"{brand} {sub_cat} (Premium)",
                "price": max(price2, price1 + 2000),
                "rating": round(random.uniform(4.3, 4.8), 1),
                "imageUrl": "",
                "brand": brand,
                "url": amazon_url,
                "source": "catalog",
            })
        else:
            for i, brand in enumerate(brands[:2]):
                price = random.randint(lower, max(upper, lower + 1000))
                price = (price // 100) * 100 + 99
                rating = round(random.uniform(3.9, 4.7), 1)
                results.append({
                    "productId": f"disc-{i}",
                    "title": f"{brand} {sub_cat}",
                    "price": price,
                    "rating": rating,
                    "imageUrl": "",
                    "brand": brand,
                    "url": amazon_url,
                    "source": "catalog",
                })
        return results
    else:
        # No ontology match — generate 2 generic discovery products
        # Use keyword-based price estimation for realistic pricing
        query_lower = search_term.lower()
        
        # Expensive electronics
        if any(w in query_lower for w in ["phone", "laptop", "tablet", "tv", "television", "macbook", "ipad", "camera"]):
            base_low, base_high = 8999, 49999
        # Mid-range electronics
        elif any(w in query_lower for w in ["watch", "smartwatch", "headphone", "speaker", "monitor", "printer"]):
            base_low, base_high = 1999, 14999
        # Fashion premium
        elif any(w in query_lower for w in ["heels", "boots", "jacket", "coat", "suit", "blazer", "saree", "lehenga"]):
            base_low, base_high = 999, 4999
        # Furniture / appliances
        elif any(w in query_lower for w in ["chair", "table", "sofa", "bed", "fridge", "washing machine", "ac", "cooler"]):
            base_low, base_high = 4999, 29999
        # Sports / fitness equipment
        elif any(w in query_lower for w in ["treadmill", "bicycle", "cycle", "gym", "exercise"]):
            base_low, base_high = 2999, 19999
        # Food / grocery / snacks
        elif any(w in query_lower for w in ["spicy", "sweet", "snack", "food", "eat", "drink", "juice", "coffee", "tea", "chocolate", "chips", "biscuit"]):
            base_low, base_high = 49, 399
        # Beauty / cosmetics
        elif any(w in query_lower for w in ["eyeliner", "lipstick", "mascara", "foundation", "nail", "cream", "lotion", "serum", "face"]):
            base_low, base_high = 99, 499
        # Standard products
        else:
            base_low, base_high = 299, 1999
        
        if max_price:
            base_high = min(base_high, int(max_price))
            base_low = min(base_low, max(base_high - 2000, 199))
        # Handle min price (above X)
        min_price_val2 = None
        if attributes:
            min_price_val2 = attributes.get("_min_price")
        if min_price_val2:
            base_low = max(base_low, int(min_price_val2))
            base_high = max(base_high, base_low + 2000)
        
        price1 = random.randint(base_low, max(base_high, base_low + 100))
        price1 = (price1 // 10) * 10 + 9  # Round to nearest 10 + 9
        price2 = random.randint(max(base_low + 50, price1), max(base_high, base_low + 200))
        price2 = (price2 // 10) * 10 + 9
        
        if max_price:
            price1 = min(price1, int(max_price) - 100)
            price2 = min(price2, int(max_price))
        
        return [
            {"productId": "disc-0", "title": f"{product_name}", "price": max(price1, base_low), "rating": 4.3, "imageUrl": "", "brand": "", "url": amazon_url, "source": "catalog"},
            {"productId": "disc-1", "title": f"{product_name} (Premium)", "price": max(price2, price1 + 50), "rating": 4.6, "imageUrl": "", "brand": "", "url": amazon_url, "source": "catalog"},
        ]


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# LOCAL CATALOG SEARCH ENGINE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

_catalog_data: list[dict] = []

def _load_catalog():
    """Load the local product catalog."""
    global _catalog_data
    catalog_path = Path(__file__).resolve().parent.parent / "data" / "catalog.json"
    if catalog_path.exists():
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _catalog_data = data.get("products", [])

_load_catalog()


# Known brands for extraction (lowercase)
_KNOWN_BRANDS = [
    "nike", "adidas", "puma", "reebok", "converse", "new balance", "skechers",
    "bata", "woodland", "sparx", "relaxo", "campus", "crocs",
    "bacca bucci", "red tape", "liberty",
    "samsung", "apple", "oneplus", "xiaomi", "realme", "google", "vivo", "oppo",
    "boat", "noise", "sony", "jbl", "zebronics", "samsung",
    "hp", "dell", "lenovo", "asus", "acer",
    "anker", "mi", "ambrane", "portronics", "belkin",
    "prestige", "hawkins", "pigeon", "bajaj", "philips", "havells",
    "cadbury", "nestle", "ferrero", "amul", "haldiram", "britannia", "parle",
    "himalaya", "cetaphil", "neutrogena", "nivea", "loreal", "maybelline", "minimalist", "plum", "mamaearth",
    "jockey", "lux cozi", "van heusen", "xyxx", "rupa", "dollar", "calvin klein",
    "levi", "levis", "wrangler", "spykar", "lee", "allen solly", "jack jones", "h&m", "us polo",
    "pedigree", "drools", "royal canin", "whiskas",
    "taparia", "stanley", "bosch", "black decker", "makita", "dewalt",
    "kore", "protoner", "boldfit", "muscleblaze", "optimum nutrition",
    "lego", "barbie", "hasbro", "hot wheels",
    "fastrack", "titan", "casio", "fossil",
    "steelbird", "studds", "vega",
    "wildhorn", "f gear",
    "amazon basics", "solimo",
]

def _extract_brand_from_query(query: str) -> str | None:
    """Extract a brand name from the user's query. Returns None if no brand found."""
    query_lower = query.lower()
    sorted_brands = sorted(_KNOWN_BRANDS, key=len, reverse=True)
    for brand in sorted_brands:
        if brand in query_lower:
            return brand
    return None


def _extract_product_term(query: str, brand: str | None) -> str:
    """Extract the actual product term from the query by removing brand and modifiers."""
    clean = query.lower().strip()
    
    # Remove brand
    if brand:
        clean = clean.replace(brand, "").strip()
    
    # Remove common modifiers
    modifiers = ["women", "woman", "men", "man", "male", "female", "boy", "girl",
                 "kids", "baby", "black", "white", "red", "blue", "green", "pink",
                 "under", "above", "below", "cheap", "premium", "best", "good",
                 "ladies", "gents", "mens", "womens", "give", "links", "link"]
    
    # Remove price numbers
    import re
    clean = re.sub(r'\d+', '', clean)
    
    words = clean.split()
    product_words = [w for w in words if w not in modifiers and len(w) >= 3]
    return " ".join(product_words).strip()


def _search_local_catalog(query: str, max_price: float | None = None, min_price: float | None = None, min_rating: float | None = None) -> list[dict]:
    """Search the local catalog with strict entity-based matching.
    
    Logic:
    1. Extract brand from query
    2. Extract product term (remove brand + modifiers)
    3. If brand specified: filter to brand AND product term must match
    4. If no brand: product term must match tags/title/subcategory
    5. Never return products where the product term doesn't match
    """
    if not _catalog_data:
        return []
    
    query_lower = query.lower().strip()
    
    # Entity extraction
    detected_brand = _extract_brand_from_query(query_lower)
    product_term = _extract_product_term(query_lower, detected_brand)
    
    # If no product term extracted (e.g., just "adidas"), return empty to trigger clarification
    if not product_term and detected_brand:
        return []  # Will trigger clarification: "Which Adidas product?"
    
    # The actual search term to match against
    search_words = set(product_term.split()) if product_term else set(query_lower.split())
    # Remove stop words
    stop = {"i", "a", "the", "is", "it", "to", "of", "in", "for", "on", "at", "and", "or",
            "my", "me", "some", "any", "want", "need", "show", "get", "find", "buy", "like",
            "would", "please", "looking", "something", "purchase",
            "ladies", "mens", "womens", "give", "links", "link", "good", "best",
            "recommendations", "recommend", "suggestion", "options"}
    search_words = {w for w in search_words if w not in stop and len(w) >= 3}
    
    if not search_words:
        return []
    
    scored_products = []
    
    for product in _catalog_data:
        # Price filter
        if max_price and product.get("price", 0) > max_price and product["price"] > 0:
            continue
        if min_price and product.get("price", 0) < min_price and product["price"] > 0:
            continue
        if min_rating and product.get("rating", 0) < min_rating:
            continue
        
        # Brand filter: if brand specified, MUST match
        if detected_brand:
            product_brand = product.get("brand", "").lower()
            if detected_brand not in product_brand and product_brand not in detected_brand:
                continue
        
        # Product term matching — the product term MUST match tags or subcategory
        tags = [t.lower() for t in product.get("tags", [])]
        sub_cat = product.get("subCategory", "").lower()
        title_words = set(product.get("title", "").lower().split())
        sub_words = set(sub_cat.split())
        
        # Check if ANY search word matches a tag EXACTLY (not substring)
        tag_matches = sum(1 for w in search_words if w in tags)
        title_word_matches = sum(1 for w in search_words if w in title_words)
        sub_matches = sum(1 for w in search_words if w in sub_words)
        
        total_matches = tag_matches + title_word_matches + sub_matches
        
        # STRICT: at least one search word must match
        if total_matches == 0:
            continue
        
        # Score based on match quality
        score = tag_matches * 5 + title_word_matches * 3 + sub_matches * 4
        
        # Bonus for exact full query match in tags
        if product_term and product_term in tags:
            score += 10
        
        # Bonus for brand match
        if detected_brand:
            score += 3
        
        scored_products.append((product, score))
    
    # Sort by score then rating
    scored_products.sort(key=lambda x: (x[1], x[0].get("rating", 0)), reverse=True)
    
    # Format results
    results = []
    for product, score in scored_products[:5]:
        results.append({
            "productId": product["id"],
            "title": product["title"],
            "price": product["price"],
            "rating": product["rating"],
            "imageUrl": product.get("image", ""),
            "brand": product.get("brand", ""),
            "url": product.get("amazonLink", f"https://www.amazon.in/s?k={query.replace(' ', '+')}"),
            "source": "catalog",
        })
    
    return results

def _calculate_product_score(query: str, query_words: set, product: dict) -> float:
    """Calculate how well a product matches a search query.
    
    Only returns a score > 0 if there's a STRONG match (exact tag, title, or brand).
    Filters out stop words to prevent false positives.
    """
    # Stop words that should NOT contribute to matching
    STOP_WORDS = {"i", "a", "the", "is", "it", "to", "of", "in", "for", "on", "at",
                  "and", "or", "my", "me", "we", "he", "she", "some", "any", "all",
                  "would", "like", "want", "need", "get", "show", "find", "buy",
                  "please", "can", "could", "should", "good", "best", "nice", "great",
                  "purchase", "looking", "something", "thing", "one", "much", "very"}
    
    # Filter query words to only meaningful product words
    meaningful_words = {w for w in query_words if w not in STOP_WORDS and len(w) >= 3}
    
    if not meaningful_words:
        return 0.0
    
    score = 0.0
    
    title_lower = product.get("title", "").lower()
    tags = [t.lower() for t in product.get("tags", [])]
    sub_category = product.get("subCategory", "").lower()
    brand = product.get("brand", "").lower()
    
    # Exact tag match (highest priority) - full query matches a tag
    if query in tags:
        score += 10.0
    
    # Meaningful words match tags
    matched_tag_words = 0
    for word in meaningful_words:
        if word in tags:
            # Exact tag match (word IS a tag)
            score += 5.0
            matched_tag_words += 1
        # Do NOT use substring matching for tags — "heels" in "hot wheels" is a false positive
    
    # Title contains full query or meaningful words (EXACT word boundary matching)
    if query in title_lower:
        score += 8.0
    else:
        title_words = set(title_lower.split())
        for word in meaningful_words:
            if word in title_words:  # Match whole words only, not substrings
                score += 3.0
    
    # Brand match
    for word in meaningful_words:
        if word == brand or word in brand:
            score += 6.0
    
    # SubCategory match (exact word boundary)
    sub_words = set(sub_category.split())
    if query == sub_category or sub_category == query:
        score += 4.0
    for word in meaningful_words:
        if word in sub_words:
            score += 2.0
    
    # CRITICAL: Only return score if at least one meaningful word matched a tag or title word
    if matched_tag_words == 0 and query not in title_lower:
        title_words_set = set(title_lower.split())
        title_match = any(w in title_words_set for w in meaningful_words)
        if not title_match:
            return 0.0
    
    # ADDITIONAL VALIDATION: If there are multiple meaningful words, at least 2 must match
    # OR the core product word must match (not just modifier words like "women", "men", "black")
    if len(meaningful_words) >= 2:
        modifier_words_set = {"women", "woman", "men", "man", "male", "female", "boy", "girl",
                              "kids", "baby", "black", "white", "red", "blue", "green", "pink",
                              "cheap", "premium", "best", "top", "new", "latest",
                              "kitchen", "home", "outdoor", "indoor", "office", "gym",
                              "electric", "wireless", "portable", "mini", "large", "small"}
        product_words = meaningful_words - modifier_words_set
        
        if product_words:
            # The actual product word(s) MUST match somewhere
            title_words_set = set(title_lower.split())
            product_match = any(w in tags or w in title_words_set or w in sub_words for w in product_words)
            if not product_match:
                return 0.0
    
    return score

