"""Product Ontology Engine for IntentFlow.

AI-powered product understanding layer that classifies virtually any shopping
query into an Amazon-style hierarchy using ontology lookup, synonym matching,
fuzzy matching, and confidence scoring.
"""

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

_ONTOLOGY_PATH = Path(__file__).resolve().parent.parent / "data" / "ontology.json"

# Module-level cache
_ontology: dict[str, Any] = {}
_synonym_index: dict[str, str] = {}  # synonym -> product_key
_all_product_keys: list[str] = []


@dataclass
class ClassificationResult:
    """Result of classifying a shopping query."""
    topCategory: str = ""
    category: str = ""
    subCategory: str = ""
    normalizedProduct: str = ""
    confidence: float = 0.0
    matchedBy: str = "none"  # "exact", "synonym", "fuzzy", "partial"
    popularBrands: list[str] = field(default_factory=list)
    trendingProducts: list[str] = field(default_factory=list)
    isAmbiguous: bool = False
    clarificationOptions: list[str] | None = None


def _load_ontology() -> None:
    """Load the product ontology and build indexes."""
    global _ontology, _synonym_index, _all_product_keys

    with open(_ONTOLOGY_PATH, "r", encoding="utf-8") as f:
        _ontology = json.load(f)

    products = _ontology.get("products", {})
    _all_product_keys = list(products.keys())

    # Build synonym -> product_key index
    for product_key, data in products.items():
        _synonym_index[product_key] = product_key
        for synonym in data.get("synonyms", []):
            _synonym_index[synonym.lower()] = product_key


# Load on import
_load_ontology()


def _normalize_text(query: str) -> str:
    """Normalize query text: lowercase, strip, remove extra spaces."""
    text = query.lower().strip()
    text = re.sub(r"[^\w\s-]", " ", text)  # remove special chars except hyphen
    text = re.sub(r"\s+", " ", text)  # collapse multiple spaces
    return text


def _exact_lookup(normalized: str) -> ClassificationResult | None:
    """Try exact match in ontology products."""
    products = _ontology.get("products", {})
    if normalized in products:
        data = products[normalized]
        return ClassificationResult(
            topCategory=data["topCategory"],
            category=data["category"],
            subCategory=data["subCategory"],
            normalizedProduct=normalized,
            confidence=1.0,
            matchedBy="exact",
            popularBrands=data.get("popularBrands", []),
            trendingProducts=data.get("trendingProducts", []),
        )
    return None


def _synonym_lookup(normalized: str) -> ClassificationResult | None:
    """Try synonym match."""
    if normalized in _synonym_index:
        product_key = _synonym_index[normalized]
        data = _ontology["products"][product_key]
        return ClassificationResult(
            topCategory=data["topCategory"],
            category=data["category"],
            subCategory=data["subCategory"],
            normalizedProduct=product_key,
            confidence=0.9,
            matchedBy="synonym",
            popularBrands=data.get("popularBrands", []),
            trendingProducts=data.get("trendingProducts", []),
        )
    return None


def _fuzzy_match(normalized: str) -> ClassificationResult | None:
    """Try fuzzy matching using sequence similarity. Handles typos.
    
    Uses a higher threshold for short words to avoid false matches like
    'wrenches' → 'watches'.
    """
    best_match = None
    best_score = 0.0
    
    # Adaptive threshold: shorter words need higher similarity to avoid confusion
    if len(normalized) <= 5:
        threshold = 0.8
    elif len(normalized) <= 7:
        threshold = 0.72
    else:
        threshold = 0.65

    # Check against all product keys and synonyms
    all_terms = list(_synonym_index.keys())

    for term in all_terms:
        score = SequenceMatcher(None, normalized, term).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = _synonym_index[term]

    if best_match:
        data = _ontology["products"][best_match]
        return ClassificationResult(
            topCategory=data["topCategory"],
            category=data["category"],
            subCategory=data["subCategory"],
            normalizedProduct=best_match,
            confidence=round(best_score * 0.9, 2),
            matchedBy="fuzzy",
            popularBrands=data.get("popularBrands", []),
            trendingProducts=data.get("trendingProducts", []),
        )
    return None


def _partial_match(normalized: str) -> ClassificationResult | None:
    """Try partial/substring matching - check if any product key is IN the query."""
    words = normalized.split()

    # Try multi-word combinations first (longest match)
    for length in range(len(words), 0, -1):
        for i in range(len(words) - length + 1):
            phrase = " ".join(words[i:i + length])
            # Check exact in products
            if phrase in _ontology.get("products", {}):
                data = _ontology["products"][phrase]
                return ClassificationResult(
                    topCategory=data["topCategory"],
                    category=data["category"],
                    subCategory=data["subCategory"],
                    normalizedProduct=phrase,
                    confidence=0.75,
                    matchedBy="partial",
                    popularBrands=data.get("popularBrands", []),
                    trendingProducts=data.get("trendingProducts", []),
                )
            # Check synonym index
            if phrase in _synonym_index:
                product_key = _synonym_index[phrase]
                data = _ontology["products"][product_key]
                return ClassificationResult(
                    topCategory=data["topCategory"],
                    category=data["category"],
                    subCategory=data["subCategory"],
                    normalizedProduct=product_key,
                    confidence=0.7,
                    matchedBy="partial",
                    popularBrands=data.get("popularBrands", []),
                    trendingProducts=data.get("trendingProducts", []),
                )
    return None


def _check_ambiguity(normalized: str) -> list[str] | None:
    """Check if the query is ambiguous (maps to multiple product types).
    
    Only triggers if the ENTIRE query is an ambiguous term, not if it's
    a substring of a more specific query.
    """
    ambiguous = _ontology.get("ambiguousTerms", {})
    
    # First check: try to find a direct product match. If found, it's not ambiguous.
    if normalized in _ontology.get("products", {}):
        return None
    if normalized in _synonym_index:
        return None
    
    # Only match ambiguous if the full query equals the ambiguous term
    for term, options in ambiguous.items():
        if normalized == term or normalized == term + "s":
            return options
    return None


def classify(query: str, context: dict | None = None) -> ClassificationResult:
    """Classify a shopping query into the product ontology.

    Pipeline:
    1. Normalize text
    2. Check for ambiguity
    3. Exact ontology lookup
    4. Synonym matching
    5. Partial/substring matching
    6. Fuzzy matching
    7. Return with confidence score

    Args:
        query: The user's shopping query (e.g., "bicycle", "hair clips", "protein powder")
        context: Optional context dict with known category/attributes

    Returns:
        ClassificationResult with hierarchical classification and confidence.
    """
    normalized = _normalize_text(query)

    if not normalized:
        return ClassificationResult(confidence=0.0, matchedBy="none")

    # Check ambiguity first
    ambiguous_options = _check_ambiguity(normalized)
    if ambiguous_options and not context:
        return ClassificationResult(
            confidence=0.4,
            matchedBy="ambiguous",
            isAmbiguous=True,
            clarificationOptions=ambiguous_options,
        )

    # Pipeline: exact → synonym → partial → (skip fuzzy for unknown products)
    result = _exact_lookup(normalized)
    if result:
        return result

    result = _synonym_lookup(normalized)
    if result:
        return result

    result = _partial_match(normalized)
    if result:
        return result

    # Only try fuzzy match if the word is likely a TYPO of a known product
    # (very high similarity required - 0.85+)
    # This prevents "plushies" → "pliers", "condoms" → random matches
    result = _fuzzy_match(normalized)
    if result and result.confidence >= 0.75:
        return result

    # No match found — return empty (caller will use the raw query for search)
    return ClassificationResult(confidence=0.0, matchedBy="none")


def get_popular_brands(product_key: str) -> list[str]:
    """Get popular brands for a product."""
    data = _ontology.get("products", {}).get(product_key, {})
    return data.get("popularBrands", [])


def get_trending_products(product_key: str) -> list[str]:
    """Get trending products for a product type."""
    data = _ontology.get("products", {}).get(product_key, {})
    return data.get("trendingProducts", [])


def get_clarification_options(term: str) -> list[str] | None:
    """Get clarification options for an ambiguous term."""
    return _check_ambiguity(_normalize_text(term))


def get_all_top_categories() -> list[str]:
    """Get all unique top-level categories."""
    categories = set()
    for data in _ontology.get("products", {}).values():
        categories.add(data["topCategory"])
    return sorted(categories)
