"""Attribute utility functions for IntentFlow.

Provides helpers for merging extracted attributes and parsing
user intent expressions like price ranges.
"""

import re


def merge_attributes(existing: dict, new: dict) -> dict:
    """Merge new extracted attributes into the existing attribute map.

    Override semantics:
    - Keys present in `new` override the corresponding keys in `existing`.
    - Keys present in `existing` but absent from `new` are preserved unchanged.

    This ensures the most recent user intent always takes priority while
    retaining previously gathered context that hasn't been contradicted.

    Args:
        existing: The current known attributes for the session.
        new: Newly extracted attributes from the latest user message.

    Returns:
        A new dict containing the merged attributes. Neither input is mutated.

    Examples:
        >>> merge_attributes({"category": "Fashion", "brand": "Nike"}, {"brand": "Adidas"})
        {'category': 'Fashion', 'brand': 'Adidas'}

        >>> merge_attributes({"color": "red"}, {"size": "M"})
        {'color': 'red', 'size': 'M'}

        >>> merge_attributes({}, {"category": "Electronics"})
        {'category': 'Electronics'}
    """
    return {**existing, **new}


def extract_price_range(price_text: str) -> str | None:
    """Parse a user's natural-language price intent into a normalized range string.

    Supported patterns:
    - "under X" / "below X" / "less than X"  -> "0-X"
    - "above X" / "over X" / "more than X"   -> "X-999999"
    - "between X and Y" / "from X to Y"      -> "X-Y" (lower-upper)
    - "X to Y" / "X-Y"                       -> "X-Y"
    - "around X" / "about X"                 -> applies a ±20% range

    Numbers may include commas (e.g., "3,000") and optional currency symbols
    (₹, $, Rs, Rs., INR).

    Args:
        price_text: Raw text expressing the user's price intent.

    Returns:
        A normalized price range string like "0-3000" or "2000-5000",
        or None if no price intent could be parsed.

    Examples:
        >>> extract_price_range("under 3000")
        '0-3000'
        >>> extract_price_range("between 2000 and 5000")
        '2000-5000'
        >>> extract_price_range("above 10000")
        '10000-999999'
        >>> extract_price_range("around 5000")
        '4000-6000'
        >>> extract_price_range("hello world")
        None
    """
    if not price_text or not isinstance(price_text, str):
        return None

    text = price_text.strip().lower()

    # Strip common currency symbols/words
    text = re.sub(r"[₹$]", "", text)
    text = re.sub(r"\b(rs\.?|inr|rupees?)\b", "", text, flags=re.IGNORECASE)
    text = text.strip()

    def _parse_number(s: str) -> int | None:
        """Extract an integer from a string, ignoring commas."""
        s = s.strip().replace(",", "")
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None

    # Pattern: "between X and Y" or "from X to Y"
    match = re.search(r"(?:between|from)\s+([\d,]+)\s*(?:and|to)\s*([\d,]+)", text)
    if match:
        low = _parse_number(match.group(1))
        high = _parse_number(match.group(2))
        if low is not None and high is not None:
            if low > high:
                low, high = high, low
            return f"{low}-{high}"

    # Pattern: "X to Y" or "X-Y" (standalone range)
    match = re.search(r"([\d,]+)\s*(?:to|-)\s*([\d,]+)", text)
    if match:
        low = _parse_number(match.group(1))
        high = _parse_number(match.group(2))
        if low is not None and high is not None:
            if low > high:
                low, high = high, low
            return f"{low}-{high}"

    # Pattern: "under X" / "below X" / "less than X"
    match = re.search(r"(?:under|below|less\s+than|upto|up\s+to)\s+([\d,]+)", text)
    if match:
        high = _parse_number(match.group(1))
        if high is not None:
            return f"0-{high}"

    # Pattern: "above X" / "over X" / "more than X"
    match = re.search(r"(?:above|over|more\s+than|exceeding)\s+([\d,]+)", text)
    if match:
        low = _parse_number(match.group(1))
        if low is not None:
            return f"{low}-999999"

    # Pattern: "around X" / "about X" / "approximately X"
    match = re.search(r"(?:around|about|approximately|approx)\s+([\d,]+)", text)
    if match:
        center = _parse_number(match.group(1))
        if center is not None:
            margin = int(center * 0.2)
            low = max(0, center - margin)
            high = center + margin
            return f"{low}-{high}"

    return None
