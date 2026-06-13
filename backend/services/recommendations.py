"""Recommendation retrieval and formatting for IntentFlow.

Queries the product catalog based on session attributes and formats
the response matching the API schema for recommendation display.
"""

from typing import Any

from models.product import Product
from models.session import Session
from services.product_catalog import query_products


def _build_attributes_summary(attributes: dict[str, Any]) -> str:
    """Build a human-readable summary of known attributes.

    Combines known attribute values into a natural phrase, e.g.:
    "Nike running shoes under ₹3000"

    Args:
        attributes: The extracted attributes from the session.

    Returns:
        A descriptive string summarizing the known attributes.
    """
    parts: list[str] = []

    brand = attributes.get("brand")
    if brand:
        parts.append(str(brand))

    # Combine type/subcategory into product description
    subcategory = attributes.get("subcategory")
    product_type = attributes.get("type")
    if product_type and subcategory:
        parts.append(f"{product_type} {subcategory}")
    elif subcategory:
        parts.append(str(subcategory))
    elif product_type:
        parts.append(str(product_type))

    category = attributes.get("category")
    if category and not subcategory and not product_type:
        parts.append(f"{category} products")

    # Price range
    price_range = attributes.get("priceRange") or attributes.get("price")
    if price_range:
        price_str = str(price_range)
        if "-" in price_str:
            range_parts = price_str.split("-")
            if len(range_parts) == 2:
                min_p, max_p = range_parts[0].strip(), range_parts[1].strip()
                if min_p == "0":
                    parts.append(f"under ₹{max_p}")
                else:
                    parts.append(f"between ₹{min_p} and ₹{max_p}")
        elif price_str.lower().startswith("under"):
            parts.append(f"under ₹{price_str.lower().replace('under', '').strip()}")
        else:
            parts.append(f"under ₹{price_str}")

    # Size/color
    size = attributes.get("size")
    if size:
        parts.append(f"in size {size}")

    color = attributes.get("color")
    if color:
        parts.append(f"in {color}")

    if not parts:
        return "your preferences"

    return " ".join(parts)


def _format_product(product: Product) -> dict[str, Any]:
    """Format a Product into the API response schema for recommendation cards.

    Args:
        product: A Product model instance.

    Returns:
        Dictionary matching the ProductSummary API schema.
    """
    return {
        "productId": product.product_id,
        "title": product.title,
        "price": product.price,
        "rating": product.rating,
        "imageUrl": product.image_url,
    }


def get_recommendations(session: Session) -> dict[str, Any]:
    """Retrieve and format product recommendations based on session attributes.

    Queries the product catalog with the session's extracted attributes,
    returns up to 5 products sorted by rating descending (highest first),
    and generates an explanation referencing known attributes.

    If zero results are found, returns a message suggesting the user broaden
    their preferences.

    Args:
        session: The current session containing extracted_attributes.

    Returns:
        A dict matching the recommendation response schema:
        {
            "type": "recommendations",
            "text": "Based on your preference for ..., here are my top picks!",
            "products": [{"productId": ..., "title": ..., "price": ..., "rating": ..., "imageUrl": ...}]
        }
    """
    # Query catalog with session's known attributes
    matching_products = query_products(session.extracted_attributes)

    # Sort by rating descending (highest first)
    sorted_products = sorted(matching_products, key=lambda p: p.rating, reverse=True)

    # Limit to top 5
    top_products = sorted_products[:5]

    # Build attributes summary for explanation
    attributes_summary = _build_attributes_summary(session.extracted_attributes)

    # Handle zero results
    if not top_products:
        return {
            "type": "recommendations",
            "text": (
                "I couldn't find products matching all your criteria. "
                "Would you like to try a broader search? "
                "You could relax the brand or price range."
            ),
            "products": [],
        }

    # Generate explanation (max 2 sentences)
    explanation_text = f"Based on your preference for {attributes_summary}, here are my top picks!"

    return {
        "type": "recommendations",
        "text": explanation_text,
        "products": [_format_product(p) for p in top_products],
    }
