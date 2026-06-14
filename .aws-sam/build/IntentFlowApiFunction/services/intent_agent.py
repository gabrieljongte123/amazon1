"""IntentFlow Agent orchestration service.

Rebuilt with fresh intent detection pipeline:
- Every query is treated as potentially NEW intent
- Only refinements (price, color, brand changes) inherit context
- Uses raw user query for search, not reconstructed attributes
- Never leaks previous session context into new searches
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from models.session import ConversationMessage, Session
from services.bedrock_client import AgentProcessingError, invoke_bedrock
from services.compression_engine import merge_attributes, process_message
from services.product_catalog import query_products
from services.prompt_builder import build_prompt

logger = logging.getLogger(__name__)

# Internal key used to track consecutive no-extraction attempts
_NO_EXTRACT_COUNT_KEY = "_no_extract_count"

# After this many consecutive no-extract attempts, show category list
_MAX_NO_EXTRACT_ATTEMPTS = 3

# Available categories for fallback display
_AVAILABLE_CATEGORIES = ["Grocery", "Fashion", "Tools", "Electronics", "Essentials"]


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS FOR THE NEW PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def _is_pagination_command(text: str) -> bool:
    """Detect 'more'/'next' continuation commands.
    
    These mean: show MORE of the same product, not a new search.
    """
    text_lower = text.lower().strip().rstrip("!.?")
    pagination_phrases = {
        "more", "show more", "next", "show next", "more options",
        "other options", "anything else", "show others", "next page",
        "what else", "show me more", "more products", "show more options",
    }
    if text_lower in pagination_phrases:
        return True
    # "more X" where X was the previous search (e.g., "more adidas shoes")
    if text_lower.startswith("more ") and len(text_lower) > 5:
        return True
    return False


def _is_refinement(text: str) -> bool:
    """Determine if the user's message is a refinement of previous intent vs a new search.
    
    REFINEMENTS modify the existing search:
    - Price: "under 1000", "above 2000", "between 500 and 1000", "cheaper", "premium"
    - Gender/audience: "women", "men", "kids", "baby", "boys", "girls"
    - Color: "black", "red", "blue", "white", "green", etc.
    - Sorting: "top rated", "best seller", "cheapest", "newest"
    - Attributes: "noise cancelling", "waterproof", "128GB", "cotton", "leather"
    - Size: "size 9", "large", "XL", "32 inch"
    - Brand alone: "nike", "adidas" (when there's previous context)
    - Confirmations: "yes", "ok", "sure"
    
    NEW SEARCHES contain a product noun:
    - "laptop", "heels", "condoms", "gaming laptop", "baby stroller"
    """
    text_lower = text.lower().strip()
    
    # === PRICE-ONLY messages are always refinements ===
    price_only_patterns = [
        r"^(under|below|less than|within|above|over|more than|between)\s",
        r"^₹|^rs\.?\s?\d|^\d+\s*(rupee|rs|₹)",
        r"^(cheaper|cheapest|expensive|premium|budget|affordable)\b",
    ]
    for pattern in price_only_patterns:
        if re.match(pattern, text_lower):
            return True
    
    # === MODIFIER-ONLY messages are refinements ===
    # These are ONLY modifiers with no product noun
    pure_modifiers = {
        # Gender
        "women", "woman", "men", "man", "male", "female",
        "boys", "girls", "kids", "baby", "unisex",
        # Colors
        "black", "white", "red", "blue", "green", "pink", "grey", "gray",
        "brown", "navy", "beige", "yellow", "orange", "purple", "gold", "silver",
        # Sorting
        "top rated", "best seller", "most popular", "cheapest", "newest",
        "highest rated", "premium", "budget",
        # Sizes
        "small", "medium", "large", "xl", "xxl", "xs",
        # Confirmations
        "yes", "yeah", "sure", "ok", "okay", "no preference",
    }
    if text_lower in pure_modifiers:
        return True
    
    # === Attribute-only patterns ===
    attribute_patterns = [
        r"^(size|colour|color|flavour|flavor)\s",
        r"^(noise cancelling|waterproof|wireless|bluetooth|cordless)\b",
        r"^(cotton|leather|steel|plastic|wooden|metal)\b",
        r"^(128gb|256gb|512gb|1tb|64gb)\b",
        r"^(chocolate|vanilla|strawberry|mango)\s*(flavou?r)?$",
        r"^\d+\s*(kg|ml|l|inch|mm|cm|gb|tb)\b",
        r"^(make it|only|show me)\s",
        r"^in\s(black|white|red|blue|green|size|colour|color)",
    ]
    for pattern in attribute_patterns:
        if re.match(pattern, text_lower):
            return True
    
    # === Brand-only is a refinement (when context exists) ===
    from services.product_catalog import _extract_brand_from_query
    brand = _extract_brand_from_query(text_lower)
    if brand and brand == text_lower.strip():
        # The ENTIRE message is just a brand name — refinement
        return True
    
    # === If text starts with price indicator ===
    if re.match(r"^₹|^rs\.?\s?\d", text_lower):
        return True
    
    # === Everything else is a NEW search ===
    return False


def _is_greeting(text: str) -> bool:
    """Check if message is a greeting/generic (not a product query)."""
    greetings = {"hi", "hello", "hey", "help", "start", "good morning", "good evening",
                 "what can you do", "how are you"}
    return text.lower().strip() in greetings or len(text.strip()) < 2


def _is_conversation_end(text: str) -> bool:
    """Check if the user is ending the conversation or saying they don't need anything."""
    end_phrases = {
        "nothing", "no", "no thanks", "no thank you", "nope", "nah",
        "that's all", "thats all", "that is all", "done", "stop",
        "cancel", "exit", "quit", "bye", "goodbye", "good bye",
        "thanks", "thank you", "thanks a lot", "thank you so much",
        "i'm good", "im good", "all good", "not now", "maybe later",
        "no need", "no more", "that's it", "thats it",
    }
    text_lower = text.lower().strip().rstrip("!.?")
    return text_lower in end_phrases


def _clean_query_for_search(text: str) -> str:
    """Clean a user query for product search, removing filler words."""
    clean = text.lower().strip()
    
    # Remove question marks and trailing punctuation
    clean = clean.rstrip("?!.,;")
    
    # Remove price range patterns before filler cleaning
    import re as _re_clean
    clean = _re_clean.sub(r'\bbetween\s*(?:rs\.?|₹|inr)?\s*\d+\s*(?:and|to|-)\s*(?:rs\.?|₹|inr)?\s*\d+\b', '', clean)
    clean = _re_clean.sub(r'\b(?:under|below|above|over|less than|more than|within|budget)\s*(?:rs\.?|₹|inr)?\s*\d+\b', '', clean)
    clean = _re_clean.sub(r'\b(?:rs\.?|₹|inr)\s*\d+\b', '', clean)
    
    # Remove common filler phrases (order matters - longer phrases first)
    fillers = [
        "i would like to purchase", "i would like to buy", "i would like some",
        "i would like", "i'd like some", "i'd like to buy", "i'd like",
        "i want to buy", "i want to get", "i want some", "i want to eat",
        "i want to drink", "i want to wear", "i want",
        "i need some", "i need to buy", "i need",
        "can you show me", "can you find", "can you get me", "can i get",
        "show me some", "show me", "get me some", "get me",
        "find me some", "find me", "looking for some", "looking for",
        "please get", "please find", "please show",
        "i am looking for", "i'm looking for",
        "give me links for", "give me link for", "give me",
        "any recommendations", "recommendations", "any suggestions",
        "a few", "couple of", "some of",
        "if its available", "if available", "if possible",
        "that is", "which is", "that are", "which are",
        "with good rating", "with good reviews",
        "good quality", "best quality", "high quality",
        "something", "anything", "to eat", "to drink", "to wear",
        "please", "some", "any",
    ]
    for filler in fillers:
        clean = clean.replace(filler, "")
    
    # Replace "ladies" with "women" for search consistency
    clean = clean.replace("ladies", "women").replace("gents", "men")
    
    # Collapse spaces
    clean = " ".join(clean.split()).strip()
    
    return clean if clean else text.lower().strip()


def _extract_constraints(text: str) -> dict:
    """Extract refinement constraints (price, brand, color, size, sorting) from text."""
    constraints = {}
    text_lower = text.lower().strip()
    
    # Price (max)
    price_match = re.search(r"(?:under|below|less than|within|max|budget)?\s*(?:rs\.?|₹|inr)?\s*(\d+)", text_lower)
    if price_match:
        constraints["priceRange"] = f"0-{price_match.group(1)}"
    
    # Sorting / rating preference
    if any(w in text_lower for w in ["top rated", "highest rated", "best rated", "best reviews"]):
        constraints["_prefer_high_rating"] = True
    
    # Color
    colors = ["black", "white", "red", "blue", "green", "grey", "brown", "navy", 
              "pink", "purple", "orange", "yellow", "silver", "gold", "beige"]
    for color in colors:
        if color in text_lower:
            constraints["color"] = color.capitalize()
            break
    
    # Brand (common ones)
    brands = {"nike": "Nike", "adidas": "Adidas", "puma": "Puma", "samsung": "Samsung",
              "sony": "Sony", "apple": "Apple", "hp": "HP", "dell": "Dell",
              "boat": "boAt", "jbl": "JBL", "levi": "Levi's"}
    for key, brand in brands.items():
        if key in text_lower:
            constraints["brand"] = brand
            break
    
    # Size
    size_match = re.search(r"\b(xs|s|m|l|xl|xxl|xxxl|\d{1,2})\b", text_lower)
    if size_match and size_match.group(1) not in text_lower.replace(size_match.group(1), "", 1):
        constraints["size"] = size_match.group(1).upper()
    
    return constraints


def _enhance_query_with_context(query: str) -> str:
    """Enhance search query with gender/audience context.
    
    Examples:
    - "heels" → "women heels" (heels are inherently women's)
    - "women shoes" → stays as-is
    - "baby shoes" → stays as-is
    - "men underwear" → stays as-is
    """
    query_lower = query.lower().strip()
    
    # Products that are inherently gendered (add "women" if no gender specified)
    women_products = {"heels", "high heels", "stilettos", "saree", "sarees", "kurti", "kurtis", 
                      "lehenga", "bangles", "anklet", "mangalsutra"}
    
    # Check if gender/audience is already in the query
    has_gender = any(g in query_lower for g in ["men", "women", "woman", "man", "male", "female",
                                                  "boy", "girl", "kids", "baby", "infant", "child"])
    
    if not has_gender:
        for product in women_products:
            if product in query_lower:
                return f"women {query_lower}"
    
    return query_lower


def _extract_price_from_query(text: str) -> float | None:
    """Extract max price from a user query."""
    text_lower = text.lower()
    patterns = [
        r"under\s*(?:rs\.?|₹|inr)?\s*(\d+)",
        r"below\s*(?:rs\.?|₹|inr)?\s*(\d+)",
        r"less than\s*(?:rs\.?|₹|inr)?\s*(\d+)",
        r"within\s*(?:rs\.?|₹|inr)?\s*(\d+)",
        r"budget\s*(?:rs\.?|₹|inr)?\s*(\d+)",
        r"between\s*(?:rs\.?|₹|inr)?\s*\d+\s*(?:and|to|-)\s*(?:rs\.?|₹|inr)?\s*(\d+)",  # between X and Y → max=Y
    ]
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return float(match.group(1))
    return None


def _extract_min_price_from_query(text: str) -> float | None:
    """Extract minimum price from a user query (above X, over X, between X and Y)."""
    text_lower = text.lower()
    patterns = [
        r"above\s*(?:rs\.?|₹|inr)?\s*(\d+)",
        r"over\s*(?:rs\.?|₹|inr)?\s*(\d+)",
        r"more than\s*(?:rs\.?|₹|inr)?\s*(\d+)",
        r"between\s*(?:rs\.?|₹|inr)?\s*(\d+)\s*(?:and|to|-)",  # between X and Y → min=X
    ]
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return float(match.group(1))
    return None


def _build_metadata(session: Session) -> dict:
    """Build metadata dict for API response."""
    return {
        "confidenceScore": session.confidence_score,
        "extractedAttributes": {
            k: v for k, v in session.extracted_attributes.items()
            if not k.startswith("_")
        },
        "questionCount": session.question_count,
    }


def _handle_need_prediction(text: str) -> dict:
    """Handle AI need prediction questions about replenishment.
    
    Distinguishes between:
    - Consumables (groceries, personal care, cleaning, baby, pet food, medicines)
    - Durables (shoes, electronics, tools, furniture, appliances)
    
    Uses simulated purchase history for consumables.
    """
    import re
    import random
    
    text_lower = text.lower()
    
    # ═══════════════════════════════════════════════════════════════════════
    # PRODUCT CLASSIFICATION: Consumable vs Durable
    # ═══════════════════════════════════════════════════════════════════════
    
    consumable_keywords = [
        "sugar", "salt", "rice", "dal", "oil", "flour", "atta", "milk", "bread",
        "maggi", "noodles", "pasta", "cereal", "biscuit", "chips", "snack",
        "coffee", "tea", "juice", "water", "soda", "coke",
        "shampoo", "soap", "toothpaste", "toothbrush", "deodorant", "perfume",
        "facewash", "face wash", "moisturizer", "sunscreen", "lotion", "cream",
        "detergent", "dishwash", "cleaner", "wipes", "tissue", "toilet paper",
        "diaper", "baby food", "baby wipes", "formula",
        "dog food", "cat food", "pet food", "kibble",
        "medicine", "tablet", "vitamin", "supplement", "paracetamol",
        "egg", "butter", "cheese", "paneer", "curd", "yogurt",
    ]
    
    durable_keywords = [
        "headphones", "earbuds", "smartwatch", "washing machine",  # Longer first to avoid substring issues
        "shoes", "sneakers", "heels", "sandals", "boots",
        "phone", "laptop", "tablet", "speaker",
        "tv", "television", "monitor", "camera", "watch",
        "tool", "drill", "hammer", "wrench", "screwdriver",
        "chair", "table", "sofa", "bed", "mattress", "desk",
        "fridge", "microwave", "mixer", "cooler", "fan", "ac",
        "bag", "backpack", "wallet", "belt", "jacket",
    ]
    
    is_consumable = any(k in text_lower for k in consumable_keywords)
    is_durable = any(k in text_lower for k in durable_keywords)
    
    # ═══════════════════════════════════════════════════════════════════════
    # DURABLE PRODUCTS: No repeated recommendations
    # ═══════════════════════════════════════════════════════════════════════
    
    if is_durable and not is_consumable:
        product = ""
        for k in durable_keywords:
            if k in text_lower:
                product = k
                break
        
        if any(p in text_lower for p in ["should i buy", "do i need", "time to buy"]):
            days_ago = random.randint(30, 180)
            response = (
                f"You bought {product} relatively recently ({days_ago} days ago). "
                f"These products typically last much longer. No replacement needed yet! "
                f"Unless it's broken or you want an upgrade, I'd say hold off."
            )
            options = ["Show upgrades", "Continue shopping", "Not now"]
        else:
            response = (
                f"Durables like {product} don't need regular restocking. "
                f"If yours is still working fine, no need to buy another. "
                f"Want me to show you accessories or related items instead?"
            )
            options = ["Show accessories", "Continue shopping", "Not now"]
        
        return {
            "type": "question",
            "text": response,
            "options": options,
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "need_prediction"}, "questionCount": 0},
        }
    
    # ═══════════════════════════════════════════════════════════════════════
    # CONSUMABLE PRODUCTS: Use purchase history for replenishment
    # ═══════════════════════════════════════════════════════════════════════
    
    # Extract quantity if mentioned
    qty_match = re.search(r'(\d+\.?\d*)\s*(kg|g|ml|l|litre|liter|packet|pack|bottle|piece|pieces|left)', text_lower)
    quantity = None
    unit = None
    if qty_match:
        quantity = float(qty_match.group(1))
        unit = qty_match.group(2)
    
    # Detect what consumable they're asking about
    product = ""
    for k in consumable_keywords:
        if k in text_lower:
            product = k
            break
    
    # Simulate purchase history for consumables
    typical_cycles = {
        "sugar": 25, "salt": 45, "rice": 20, "dal": 15, "oil": 22,
        "flour": 18, "atta": 18, "milk": 3, "bread": 5,
        "maggi": 12, "noodles": 14, "coffee": 20, "tea": 25,
        "shampoo": 30, "soap": 20, "toothpaste": 28, "deodorant": 35,
        "facewash": 25, "face wash": 25, "moisturizer": 40, "sunscreen": 35,
        "detergent": 25, "dishwash": 20, "wipes": 14, "tissue": 10,
        "diaper": 7, "dog food": 14, "cat food": 14, "pet food": 14,
    }
    
    cycle_days = typical_cycles.get(product, 20)
    days_since_purchase = random.randint(max(1, cycle_days - 10), cycle_days + 5)
    
    # Determine stock level
    level = "moderate"  # default
    if quantity is not None:
        if unit in ("kg",):
            if quantity >= 5:
                level = "plenty"
            elif quantity >= 1:
                level = "moderate"
            else:
                level = "low"
        elif unit in ("g",):
            if quantity >= 2000:
                level = "plenty"
            elif quantity >= 500:
                level = "moderate"
            else:
                level = "low"
        elif unit in ("l", "litre", "liter"):
            if quantity >= 2:
                level = "plenty"
            elif quantity >= 0.5:
                level = "moderate"
            else:
                level = "low"
        elif unit in ("ml",):
            if quantity >= 1000:
                level = "plenty"
            elif quantity >= 200:
                level = "moderate"
            else:
                level = "low"
        elif unit in ("packet", "pack", "piece", "pieces"):
            if quantity >= 10:
                level = "plenty"
            elif quantity >= 3:
                level = "moderate"
            elif quantity >= 2:
                level = "low"
            else:
                level = "very_low"
        elif unit == "bottle":
            if quantity >= 3:
                level = "plenty"
            elif quantity >= 1:
                level = "moderate"
            else:
                level = "low"
        
        if quantity >= 10000:
            level = "plenty"
        elif quantity >= 1000 and unit in ("kg", "l", "litre", "liter"):
            level = "plenty"
    
    # Text cues override
    if "last one" in text_lower or "only one" in text_lower or "almost out" in text_lower or "running out" in text_lower:
        level = "very_low"
    elif "half" in text_lower:
        level = "moderate"
    
    # Generate response with purchase history context
    if level == "plenty":
        response = (
            f"You've got plenty of {product}! No need to buy more anytime soon. "
            f"Based on typical usage, you're probably good for another {random.randint(15, 30)} days."
        )
        options = ["Continue shopping", "Not now"]
    elif level == "moderate":
        response = (
            f"You're probably okay for now. "
            f"You last bought {product} around {days_since_purchase} days ago — "
            f"based on typical usage, you might want to reorder in about {random.randint(5, 12)} days. "
            f"I can remind you later or show options when you're ready."
        )
        options = ["Show options", "Remind me later", "Not now"]
    elif level == "low":
        response = (
            f"You're running a bit low on {product}. "
            f"You bought it about {days_since_purchase} days ago — that's close to the typical restock cycle. "
            f"Would you like me to show you some options?"
        )
        options = ["Show options", "Remind me later", "Not now"]
    else:  # very_low
        response = (
            f"Sounds like you need to restock {product} soon! "
            f"It's been about {days_since_purchase} days since your last purchase. "
            f"Let me show you some options right away."
        )
        options = ["Show options", "Not now"]
    
    return {
        "type": "question",
        "text": response,
        "options": options,
        "products": None,
        "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "need_prediction", "_product": product}, "questionCount": 0},
    }


def _classify_multi_stage_intent(text: str, session=None) -> dict | None:
    """Multi-stage intent classification pipeline.
    
    Pipeline: Query → Intent Type → Need Extraction → Category Mapping → Response
    
    Intent types:
      COMPLEMENTARY  — user has/bought a product, wants related items
      LIFESTYLE      — situation/occasion/weather/activity described
      FOOD           — hunger/meal/snack need
      DECISION       — comparative or ambiguous choice question
      REPLENISHMENT  — running out of consumables
      (None)         — general shopping, continues to main product pipeline
    
    Rules:
      - Never use raw query as product search term
      - Always infer underlying need first
      - Low confidence → ask clarifying question
    """
    t = text.lower().strip().rstrip("?!.")
    
    # ───────────────────────────────────────────────────────────────────────
    # PRONOUN RESOLUTION — "what goes with it?" → resolve to last product
    # ───────────────────────────────────────────────────────────────────────
    
    companion_pronoun_patterns = [
        r"(?:what|which|anything)\s+(?:goes?|pairs?|works?)\s+(?:well\s+)?with\s+(?:it|this|that)",
        r"(?:suggest|recommend)\s+(?:something\s+)?(?:to go|for|with)\s+(?:it|this|that)",
        r"what\s+(?:would|could|should)\s+(?:go|pair)\s+(?:well\s+)?with\s+(?:it|this|that)",
        r"go\s+along\s+with\s+(?:it|this|that)",
        r"along\s+with\s+(?:it|this|that)",
        r"what\s+(?:about|else)\s+(?:for|with)\s+(?:it|this|that)",
        r"what\s+(?:would\s+)?go\s+(?:along\s+)?with\s+(?:it|this|that)",
    ]
    
    for _pp in companion_pronoun_patterns:
        if re.search(_pp, t):
            _resolved = None
            if session:
                _last = session.extracted_attributes.get("_last_product", {})
                _sterm = session.extracted_attributes.get("_search_term", "")
                if _last and _last.get("title"):
                    _stop = {"with", "and", "the", "for", "from", "of", "a", "an", "by", "in"}
                    _words = [w for w in _last["title"].lower().split() if len(w) > 2 and w not in _stop][:2]
                    _resolved = " ".join(_words) if _words else _sterm
                elif _sterm:
                    _resolved = _sterm
            if _resolved:
                return _classify_multi_stage_intent(f"what goes well with {_resolved}", session)
            else:
                return {
                    "type": "question",
                    "text": "What product are you referring to? I'd love to suggest complementary items!",
                    "options": None,
                    "products": None,
                    "metadata": {"confidenceScore": 0.3, "extractedAttributes": {"_action": "clarify_pronoun"}, "questionCount": 0},
                }
    
    # ───────────────────────────────────────────────────────────────────────
    # COMPLEMENTARY / BASKET COMPLETION INTENT
    # "I bought X" / "I have X" / "I got X" → suggest what goes with it
    # ───────────────────────────────────────────────────────────────────────
    
    # Known complementary pairing map: product → what completes the basket
    complementary_map = {
        # Grocery / consumables
        "sugar": ["tea", "coffee", "milk", "baking flour", "biscuits"],
        "tea": ["sugar", "milk", "tea strainer", "biscuits", "electric kettle"],
        "coffee": ["sugar", "milk", "coffee mug", "coffee filter", "biscuits"],
        "pasta": ["pasta sauce", "parmesan cheese", "olive oil", "garlic", "herbs"],
        "rice": ["dal", "cooking oil", "spices", "pressure cooker", "salt"],
        "bread": ["butter", "jam", "peanut butter", "eggs", "cheese"],
        "oats": ["milk", "honey", "protein powder", "fruits", "almonds"],
        "flour": ["sugar", "baking powder", "butter", "eggs", "vanilla essence"],
        "milk": ["tea", "coffee", "sugar", "cereal", "protein powder"],
        # Electronics
        "laptop": ["laptop bag", "wireless mouse", "cooling pad", "USB hub", "laptop stand"],
        "macbook": ["MacBook sleeve", "USB-C hub", "wireless mouse", "laptop stand", "AirPods"],
        "phone": ["phone case", "screen protector", "charger", "earbuds", "power bank"],
        "iphone": ["iPhone case", "AirPods", "MagSafe charger", "screen protector", "power bank"],
        "headphones": ["headphone stand", "carry case", "extra ear pads", "cable extension", "foam tips"],
        "earbuds": ["carry case", "ear tips", "cleaning kit", "cable", "charging dock"],
        "tablet": ["tablet case", "stylus pen", "screen protector", "bluetooth keyboard", "stand"],
        "ipad": ["iPad case", "Apple Pencil", "screen protector", "keyboard folio", "stand"],
        "camera": ["camera bag", "memory card", "tripod", "lens filter", "extra battery"],
        "printer": ["printer ink", "A4 paper", "USB cable", "ink cartridge", "paper tray"],
        "tv": ["HDMI cable", "soundbar", "TV mount", "streaming device", "surge protector"],
        "gaming console": ["extra controller", "gaming headset", "HDMI cable", "charging dock", "game titles"],
        "keyboard": ["wrist rest", "keycap set", "desk mat", "cable management", "monitor riser"],
        "monitor": ["HDMI cable", "monitor stand", "anti-glare screen", "cable management", "desk lamp"],
        # Fashion
        "jeans": ["belt", "t-shirt", "casual shoes", "socks", "jacket"],
        "saree": ["saree blouse", "petticoat", "safety pins", "heels", "jewellery"],
        "sneakers": ["socks", "sneaker cleaner", "extra laces", "insoles", "shoe bag"],
        "heels": ["anti-slip pads", "heel cushion", "formal dress", "clutch", "foot cream"],
        # Tools
        "drill": ["drill bits", "safety goggles", "measuring tape", "wall plugs", "extension cord"],
        "wrench": ["pliers", "screwdriver set", "socket set", "nut bolt set", "tool box"],
        "hammer": ["nails", "chisel set", "safety goggles", "tool belt", "measuring tape"],
        # Baby / pets
        "baby": ["baby wipes", "diaper rash cream", "baby powder", "feeding bottle", "baby monitor"],
        "dog": ["dog food", "leash", "dog collar", "chew toys", "dog shampoo"],
        "cat": ["cat food", "litter box", "cat toys", "scratching post", "cat bed"],
    }
    
    # Patterns: "I bought X", "I have X", "I got X", "I purchased X", "I own X"
    comp_patterns = [
        r"i\s+(?:just\s+)?(?:bought|purchased|got|ordered|have|own(?:ed)?|received)\s+(?:a\s+|an\s+|my\s+)?(.+?)(?:\.|$|,|\s+what|\s+which|\s+anything|\s+any)",
        r"(?:what|anything|which)\s+(?:goes|pairs?)\s+(?:well\s+)?with\s+(.+)",
        r"(?:what|anything)\s+(?:else)?\s+(?:do i need|should i get|goes with)\s+(?:with\s+)?(.+)",
        r"i\s+(?:just\s+)?bought\s+(.+)",
        r"(?:accessories|what to get)\s+(?:for|with)\s+(.+)",
        r"(.+?)\s+accessories$",
    ]
    
    for pattern in comp_patterns:
        match = re.search(pattern, t)
        if match:
            base = match.group(1).strip().rstrip("?!.,")
            # Strip common fillers
            for fw in ["a ", "an ", "my ", "the ", "some "]:
                if base.startswith(fw):
                    base = base[len(fw):]
            
            # Find complementary items
            items = None
            for key, vals in complementary_map.items():
                if key in base:
                    items = vals
                    break
            
            if items:
                return {
                    "type": "question",
                    "text": f"Great choice! Here's what pairs well with {base}:",
                    "options": items[:5],
                    "products": None,
                    "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "complementary", "_base": base}, "questionCount": 0},
                }
            else:
                # Unknown base — ask what category of companion they want
                return {
                    "type": "question",
                    "text": f"What kind of items are you looking for to go with {base}?",
                    "options": ["Accessories", "Essentials", "Upgrades", "Cleaning / maintenance", "Something else"],
                    "products": None,
                    "metadata": {"confidenceScore": 0.5, "extractedAttributes": {"_action": "complementary_clarify", "_base": base}, "questionCount": 0},
                }
    
    # ───────────────────────────────────────────────────────────────────────
    # REPLENISHMENT INTENT
    # "Running out of X", "Need to restock X", "Out of X"
    # ───────────────────────────────────────────────────────────────────────
    
    replenishment_patterns = [
        r"(?:running out|out)\s+of\s+(.+)",
        r"(?:need to|need|want to)\s+restock\s+(.+)",
        r"(?:almost|nearly)\s+(?:out of|finished|done with)\s+(.+)",
        r"(?:ran out|finished)\s+(?:of\s+)?(.+)",
        r"(?:last one|last pack|last bottle)\s+(?:of\s+)?(.+)",
        r"need\s+more\s+(.+)",
        r"reorder\s+(.+)",
    ]
    
    for pattern in replenishment_patterns:
        match = re.search(pattern, t)
        if match:
            item = match.group(1).strip().rstrip("?!.,")
            return {
                "type": "question",
                "text": f"Let me help you restock {item}. How urgent is it?",
                "options": [f"Order {item} now", f"Show {item} options", "Remind me later"],
                "products": None,
                "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "replenishment", "_item": item}, "questionCount": 0},
            }
    
    # ───────────────────────────────────────────────────────────────────────
    # FOOD / HUNGER INTENT
    # ───────────────────────────────────────────────────────────────────────
    
    food_triggers = [
        r"i'?m\s+(?:hungry|starving|craving|famished)",
        r"(?:feeling|feel)\s+(?:hungry|peckish)",
        r"(?:suggest|recommend|want)\s+(?:snacks?|food|meal|something to eat|something to drink)",
        r"what\s+(?:should i|can i|to)\s+(?:eat|cook|order|have)\s*(?:tonight|today|now)?",
        r"(?:healthy|quick|tasty)\s+(?:breakfast|lunch|dinner|snack)\s+(?:ideas?|options?)",
        r"(?:snack|meal|breakfast|lunch|dinner)\s+(?:ideas?|suggestions?|options?)",
        r"something\s+(?:to eat|to snack|tasty|yummy|delicious)",
        r"i\s+(?:want|need|am craving)\s+(?:something\s+)?(?:sweet|spicy|crunchy|salty|healthy|light)",
    ]
    
    food_suggestions = {
        "snack": ["Chips & Namkeen", "Protein bars", "Mixed nuts & dry fruits", "Biscuits & cookies", "Dark chocolate"],
        "breakfast": ["Oats & muesli", "Bread & spreads", "Poha & upma mix", "Eggs", "Fruit juice"],
        "lunch": ["Ready-to-eat dal", "Instant rice meals", "Pasta & sauce", "Soups", "Flatbread"],
        "dinner": ["Pasta & sauce", "Frozen meals", "Instant noodles", "Cooking essentials", "Spice mixes"],
        "healthy": ["Protein bars", "Roasted makhana", "Green tea", "Mixed dry fruits", "Oats"],
        "sweet": ["Chocolate", "Biscuits", "Halwa mix", "Mithai", "Dried fruits"],
        "spicy": ["Spicy chips", "Bhujia", "Masala peanuts", "Hot sauce", "Spicy instant noodles"],
        "hungry": ["Instant noodles", "Ready-to-eat meals", "Biscuits", "Chips", "Protein bars"],
    }
    
    for pattern in food_triggers:
        if re.search(pattern, t):
            matched_key = "hungry"
            for key in ["snack", "breakfast", "lunch", "dinner", "healthy", "sweet", "spicy"]:
                if key in t:
                    matched_key = key
                    break
            items = food_suggestions[matched_key]
            return {
                "type": "question",
                "text": f"Here are some {matched_key} options to satisfy that craving! 😋",
                "options": items,
                "products": None,
                "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "food_recommendation", "_craving": matched_key}, "questionCount": 0},
            }
    
    # ───────────────────────────────────────────────────────────────────────
    # LIFESTYLE / SITUATIONAL INTENT
    # Maps situation → product categories
    # ───────────────────────────────────────────────────────────────────────
    
    lifestyle_map = {
        "sunny":         ("sunny day outfit", ["Sunglasses", "Sunscreen SPF 50", "Cotton t-shirt", "Cap or hat", "Light sneakers"]),
        "rainy":         ("rainy weather essentials", ["Umbrella", "Waterproof jacket", "Rain boots", "Waterproof bag cover", "Quick-dry clothes"]),
        "winter":        ("winter essentials", ["Warm jacket", "Thermal inner wear", "Woolen socks", "Gloves", "Beanie cap"]),
        "summer":        ("summer essentials", ["Cotton clothes", "Sunglasses", "Sunscreen", "Water bottle", "Flip flops"]),
        "cold":          ("cold weather essentials", ["Hoodie", "Warm jacket", "Thermals", "Blanket", "Hot water bottle"]),
        "office":        ("office essentials", ["Formal shirt", "Trousers / formal pants", "Laptop bag", "Belt", "Formal shoes"]),
        "gym":           ("gym essentials", ["Gym shorts", "Sports t-shirt", "Running shoes", "Water bottle", "Resistance bands"]),
        "beach":         ("beach essentials", ["Swimwear", "Sunscreen", "Beach towel", "Flip flops", "Waterproof bag"]),
        "picnic":        ("picnic essentials", ["Picnic mat", "Water bottle", "Snack box", "Portable Bluetooth speaker", "Sunscreen"]),
        "travel":        ("travel essentials", ["Backpack", "Neck pillow", "Power bank", "Earbuds", "Packing cubes"]),
        "camping":       ("camping essentials", ["Tent", "Sleeping bag", "Flashlight / headlamp", "Portable stove", "First aid kit"]),
        "hiking":        ("hiking essentials", ["Hiking shoes", "Trekking backpack", "Water bottle", "Trekking pole", "Rain jacket"]),
        "party":         ("party essentials", ["Party wear outfit", "Perfume", "Accessories", "Heels or loafers", "Clutch"]),
        "wedding":       ("wedding essentials", ["Ethnic wear", "Jewellery", "Heels or formal shoes", "Clutch", "Perfume"]),
        "interview":     ("interview outfit", ["Formal blazer", "Shirt", "Trousers", "Formal shoes", "Portfolio bag"]),
        "date":          ("date night picks", ["Smart casual outfit", "Perfume", "Grooming kit", "Wallet", "Nice shoes"]),
        "movie night":   ("movie night must-haves", ["Popcorn", "Cozy blanket", "Snacks & drinks", "Comfy pajamas", "Air freshener"]),
        "hosting guests": ("host essentials", ["Snacks & beverages", "Paper plates & napkins", "Candles", "Air freshener", "Disposable cups"]),
        "college":       ("college essentials", ["Backpack", "Notebook set", "Water bottle", "Earbuds", "Laptop sleeve"]),
        "work from home": ("WFH essentials", ["Laptop stand", "Wireless keyboard", "Noise-cancelling earbuds", "Desk lamp", "Blue light glasses"]),
    }
    
    lifestyle_triggers = [
        r"what\s+(?:should i|to)\s+(?:wear|take|bring|carry|pack)",
        r"(?:suggest|recommend)\s+(?:an?\s+)?(?:outfit|clothes|wear|look|style|kit|essentials?)",
        r"(?:going|heading|planning to go|i'?m going)\s+(?:to\s+)?(?:the\s+)?(.+)",
        r"(?:i'?m at|i'?m in|at the)\s+(.+)",
        r"(?:it'?s|it is)\s+(?:sunny|rainy|cold|winter|summer|hot|warm)",
        r"(?:for|to)\s+(?:a\s+)?(?:date|party|wedding|beach|gym|office|interview|picnic|camping|hiking|travel)",
        r"(?:movie night|date night|work from home|wfh|college|office)\s+(?:essentials?|kit|must.?haves?|ideas?)?",
        r"(?:gym|travel|beach|hiking|camping|picnic|party|wedding|interview)\s+(?:starter\s+)?(?:kit|essentials?|must.?haves?)",
        r"i'?m\s+(?:going|heading|travelling)",
        r"i'?m\s+hosting\s+(?:guests?|a party|friends?)",
        r"(?:sunny|rainy|winter|summer|cold|hot|warm|monsoon)\s+(?:day|weather|season)?",
    ]
    
    # Check if any lifestyle trigger matches
    is_lifestyle = any(re.search(p, t) for p in lifestyle_triggers)
    
    if is_lifestyle:
        # Find the best matching lifestyle category
        matched_label = None
        matched_items = None
        for key, (label, items) in lifestyle_map.items():
            if key in t:
                matched_label = label
                matched_items = items
                break
        
        if matched_label and matched_items:
            return {
                "type": "question",
                "text": f"Here's your {matched_label} checklist! Tap anything to shop it:",
                "options": matched_items,
                "products": None,
                "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "lifestyle_recommendation", "_context": matched_label}, "questionCount": 0},
            }
        else:
            # Lifestyle detected but context unknown — clarify
            return {
                "type": "question",
                "text": "I'd love to help you prepare! What's the occasion or situation?",
                "options": ["Office / Work", "Gym / Fitness", "Travel", "Party / Wedding", "Beach / Outdoors", "Bad weather", "Something else"],
                "products": None,
                "metadata": {"confidenceScore": 0.5, "extractedAttributes": {"_action": "lifestyle_clarification"}, "questionCount": 0},
            }
    
    # ───────────────────────────────────────────────────────────────────────
    # DECISION SUPPORT INTENT
    # Comparative / "which is better" / "help me choose" queries
    # ───────────────────────────────────────────────────────────────────────
    
    decision_triggers = [
        r"which\s+is\s+(?:better|best|good)\s+for\s+(.+)",
        r"(?:what should i|help me)\s+(?:choose|pick|select|buy)\s+(?:between|for)\s*(.+)?",
        r"(?:i don'?t know|not sure)\s+(?:what|which)\s+to\s+(?:buy|choose|get|pick)",
        r"(?:recommend|suggest)\s+(?:something|one|a\s+good)\s+(?:for|to)\s+(.+)",
        r"what'?s\s+(?:a\s+)?(?:good|best|better)\s+(.+)\s+for\s+(.+)",
        r"(?:beginner|starter|first\s+time|entry.?level)\s+(.+)",
    ]
    
    for pattern in decision_triggers:
        match = re.search(pattern, t)
        if match:
            context = (match.group(1) or "").strip() if match.lastindex and match.lastindex >= 1 else ""
            # Ask a single clarifying question to narrow down
            clarify_text = "I'd like to help you choose the right one! What's most important to you?"
            if context:
                clarify_text = f"I'd like to help you choose the right {context}! What matters most?"
            return {
                "type": "question",
                "text": clarify_text,
                "options": ["Budget / Best value", "Top-rated quality", "Beginner-friendly", "Most popular", "Latest model"],
                "products": None,
                "metadata": {"confidenceScore": 0.8, "extractedAttributes": {"_action": "decision_support", "_context": context}, "questionCount": 0},
            }
    
    # No multi-stage classification matched — fall through to general product search
    return None


def _classify_high_level_intent(text_lower: str, session=None) -> dict | None:
    """Delegates to the multi-stage classification pipeline."""
    return _classify_multi_stage_intent(text_lower, session)


def _detect_action_command(text: str, session: Session = None) -> dict | None:
    """Detect voice/chat action commands and conversational intents.
    
    Priority:
    1. Conversational end (nothing, no thanks, done, bye)
    2. Cart/purchase commands (add to cart, buy now, checkout)
    3. Navigation commands (continue shopping, view cart)
    
    Returns a response dict if detected, None for shopping intents.
    """
    text_lower = text.lower().strip().rstrip("!.?")
    
    # ═══════════════════════════════════════════════════════════════════════
    # PRIORITY 0: Option button responses that should NOT end the conversation
    # ═══════════════════════════════════════════════════════════════════════
    
    # "Remind me later" / "Not now" from need prediction — dismiss but keep chatting
    if text_lower in ("remind me later", "not now"):
        return {
            "type": "question",
            "text": "Got it! I'll keep that in mind. What else can I help you with?",
            "options": None,
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "dismiss"}, "questionCount": 0},
        }
    
    # ═══════════════════════════════════════════════════════════════════════
    # PRIORITY 1: Conversational end-of-conversation intents
    # ═══════════════════════════════════════════════════════════════════════
    if _is_conversation_end(text):
        return {
            "type": "question",
            "text": "Glad I could help! Feel free to come back anytime you need to shop. Happy shopping! 🎉",
            "options": None,
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "end_conversation"}, "questionCount": 0},
        }
    
    # Add to cart commands (including "Add [product] to cart")
    add_cart_patterns = [
        "add to cart", "add it to cart", "add this to cart",
        "add the first", "add the second", "add the third",
        "add that", "put in cart", "cart it", "add it",
    ]
    # Check if message contains "add" and "cart" anywhere, OR "add [product name] to cart"
    is_add_to_cart = ("add" in text_lower and "cart" in text_lower) or any(p in text_lower for p in add_cart_patterns)
    if is_add_to_cart:
        # Get "frequently bought together" suggestions
        from services.bought_together import get_bought_together
        # Extract product name from "Add [product title] to cart" button click
        product_title = ""
        if "to cart" in text_lower and text_lower.startswith("add "):
            product_title = text_lower.replace("add ", "", 1).replace(" to cart", "").strip()
        
        # Use the last search term from session for context
        search_term = ""
        if session and session.extracted_attributes.get("_search_term"):
            search_term = session.extracted_attributes["_search_term"]
        elif product_title:
            search_term = product_title
        else:
            # Extract from text
            for word in text_lower.replace("add", "").replace("to cart", "").replace("the", "").replace("first", "").replace("second", "").split():
                if len(word) > 3:
                    search_term = word
                    break
        
        # Add the product to cart in session
        if session:
            cart = session.extracted_attributes.get("_cart", [])
            if product_title:
                # Use the specific product title from button click
                cart.append({"title": product_title.title(), "price": session.extracted_attributes.get("_last_product", {}).get("price", 0)})
            else:
                last_product = session.extracted_attributes.get("_last_product")
                if last_product:
                    cart.append(last_product)
                elif search_term:
                    cart.append({"title": search_term.title(), "price": 0})
            session.extracted_attributes["_cart"] = cart
        
        bought_together = get_bought_together(search_term) if search_term else []
        
        if bought_together:
            suggestions = ", ".join(bought_together[:3])
            response_text = (
                f"✅ Added to your cart!\n\n"
                f"🛍️ Frequently bought together:\n"
                f"• {bought_together[0].title()}\n"
                f"• {bought_together[1].title() if len(bought_together) > 1 else ''}\n"
                f"• {bought_together[2].title() if len(bought_together) > 2 else ''}\n\n"
                f"Would you like to add any of these?"
            )
            options_list = [f"Add {b.title()}" for b in bought_together[:3]] + ["Checkout", "Continue shopping"]
        else:
            response_text = "✅ Added to your cart! Would you like to continue shopping or checkout?"
            options_list = ["Continue shopping", "Checkout", "View cart"]
        
        return {
            "type": "question",
            "text": response_text,
            "options": options_list,
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "add_to_cart"}, "questionCount": 0},
        }
    
    # Buy now commands (including "Buy [product name]")
    buy_patterns = ["buy now", "buy it", "buy this", "purchase it", "purchase this", "order it", "order this", "buy the first", "buy the second"]
    is_buy_command = any(p in text_lower for p in buy_patterns)
    # Also catch "Buy Samsung Smartphones" pattern (starts with "buy " + has a product name)
    if not is_buy_command and text_lower.startswith("buy ") and len(text_lower) > 5:
        is_buy_command = True
    if is_buy_command:
        return {
            "type": "question",
            "text": "🛒 Proceeding to checkout!\n\n📦 Order Summary:\n• Your selected item\n• Shipping: FREE\n• Estimated delivery: 2-3 business days\n\nSay 'Confirm order' or 'Place order' to complete your purchase.",
            "options": ["Place order", "Go back to shopping"],
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "buy_now"}, "questionCount": 0},
        }
    
    # Checkout / place order commands
    checkout_patterns = ["checkout", "check out", "place order", "confirm order", "pay now", "complete order", "proceed to pay"]
    for pattern in checkout_patterns:
        if pattern in text_lower:
            order_id = "AMZ" + str(abs(hash(text)) % 999999).zfill(6)
            return {
                "type": "question",
                "text": f"🎉 Order placed successfully!\n\n📋 Order #{order_id}\n📦 Estimated delivery: 2-3 business days\n💳 Payment: Cash on Delivery\n\nThank you for shopping with Amazon IntentFlow!",
                "options": ["Continue shopping", "Track order"],
                "products": None,
                "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "order_placed", "_orderId": order_id}, "questionCount": 0},
            }
    
    # View cart commands
    cart_patterns = ["view cart", "show cart", "my cart", "what's in my cart", "open cart", "see cart"]
    for pattern in cart_patterns:
        if pattern in text_lower:
            # Get cart items from session
            cart_items = []
            if session:
                cart_items = session.extracted_attributes.get("_cart", [])
            
            if cart_items:
                cart_text = "🛒 **Your Cart:**\n\n"
                total = 0
                for i, item in enumerate(cart_items, 1):
                    price = item.get("price", 0)
                    cart_text += f"{i}. {item['title']}"
                    if price > 0:
                        cart_text += f" — ₹{price:,}"
                        total += price
                    cart_text += "\n"
                cart_text += f"\n💰 Subtotal: ₹{total:,}"
                cart_text += f"\n📦 Shipping: FREE"
                cart_text += f"\n━━━━━━━━━━━━━━"
                cart_text += f"\n**Total: ₹{total:,}**"
                cart_text += f"\n\nSay 'Checkout' to place your order!"
            else:
                cart_text = "🛒 Your cart is empty! Start shopping by telling me what you need."
            
            return {
                "type": "question",
                "text": cart_text,
                "options": ["Checkout", "Continue shopping", "Clear cart"] if cart_items else ["Continue shopping"],
                "products": None,
                "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "view_cart"}, "questionCount": 0},
            }
    
    # Clear cart
    if "clear cart" in text_lower or "empty cart" in text_lower or "remove all" in text_lower:
        if session:
            session.extracted_attributes["_cart"] = []
        return {
            "type": "question",
            "text": "🗑️ Cart cleared! What would you like to shop for?",
            "options": None,
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "clear_cart"}, "questionCount": 0},
        }
    
    # Track order
    if "track order" in text_lower or "track my order" in text_lower or "order status" in text_lower:
        return {
            "type": "question",
            "text": "📍 Your order is being prepared and will be shipped soon!\n\nStatus: Processing → Shipped → Out for Delivery → Delivered\n\nEstimated delivery: 2-3 business days.",
            "options": ["Continue shopping"],
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "track_order"}, "questionCount": 0},
        }
    
    # Continue shopping
    if "continue shopping" in text_lower or "keep shopping" in text_lower or "shop more" in text_lower:
        return {
            "type": "question",
            "text": "Great! What else can I help you find today?",
            "options": None,
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "continue"}, "questionCount": 0},
        }
    
    # New search / Try different filters (from option buttons)
    if text_lower in ("new search", "try different filters", "try again", "start over", "reset"):
        return {
            "type": "question",
            "text": "Sure! What would you like to search for?",
            "options": None,
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "new_search"}, "questionCount": 0},
        }
    
    # "Show options" from need prediction — trigger product search for the predicted product
    if text_lower == "show options":
        # If there's a predicted product in the session, search for it
        if session and session.extracted_attributes.get("_product"):
            return None  # Let it fall through to product search
        return {
            "type": "question",
            "text": "What product would you like to see options for?",
            "options": None,
            "products": None,
            "metadata": {"confidenceScore": 1.0, "extractedAttributes": {"_action": "show_options"}, "questionCount": 0},
        }
    
    # "Show upgrades" / "Show accessories" from durable need prediction
    if text_lower in ("show upgrades", "show accessories"):
        return None  # Let it fall through to product search
    
    # AI NEED PREDICTION — detect replenishment questions
    # Only trigger if this is NOT a lifestyle/situational query
    need_patterns = [
        "should i buy", "should i get", "do i need", "running low",
        "running out", "almost out", "last one", "only one left",
        "half left", "left over", "still have", "have left",
        "need to restock", "need to refill", "time to buy",
    ]
    # Guard: do not trigger need prediction on lifestyle/situational sentences
    _lifestyle_guard = any(w in text_lower for w in [
        "sunny", "rainy", "cold", "hot", "warm", "winter", "summer", "today", "weather",
        "going to", "heading to", "office", "gym", "beach", "party", "wedding", "travel",
        "movie", "date", "hiking", "camping", "hosting", "bored", "hungry", "eating",
    ])
    if not _lifestyle_guard and any(p in text_lower for p in need_patterns):
        return _handle_need_prediction(text_lower)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # HIGHER-LEVEL INTENT CLASSIFICATION
    # Classifies queries into: PRODUCT_COMPANION, LIFESTYLE_RECOMMENDATION,
    # FOOD_RECOMMENDATION, or GENERAL_SHOPPING (returns None to continue pipeline)
    # ═══════════════════════════════════════════════════════════════════════════
    
    _classified = _classify_high_level_intent(text_lower, session)
    if _classified:
        return _classified
    
    return None


def process_user_message(session: Session, text: str) -> dict:
    """Process a user message through the IntentFlow Agent pipeline.

    Orchestrates:
    1. Detect if this is a new intent or refinement of previous
    2. If new: wipe previous attributes, use raw query for search
    3. If refinement: merge new constraints into existing
    4. Search for products using the user's actual words
    5. Return results immediately when intent is clear

    Args:
        session: The current session state.
        text: The user's message text.

    Returns:
        A dict matching the API response schema:
        {type, text, options?, products?, metadata}

    Raises:
        AgentProcessingError: If Bedrock invocation fails.
    """
    from services.product_catalog import search_and_recommend
    from services.ontology_engine import classify, get_clarification_options

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 0: VOICE/CHAT ACTION COMMANDS
    # Detect commands like "buy now", "add to cart", "checkout", etc.
    # ═══════════════════════════════════════════════════════════════════════════
    
    action_result = _detect_action_command(text, session)
    if action_result:
        _append_to_history(session, "user", text)
        _append_to_history(session, "agent", action_result["text"])
        return action_result

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 0.25: "SHOW OPTIONS" from need prediction — use stored product
    # ═══════════════════════════════════════════════════════════════════════════
    
    if text.lower().strip() == "show options" and session.extracted_attributes.get("_product"):
        # Override the text with the predicted product so it triggers a real search
        text = session.extracted_attributes["_product"]
        session.extracted_attributes.pop("_product", None)

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 0.5: PAGINATION — "more" / "show more" / "next"
    # Shows next unseen products from the current search
    # ═══════════════════════════════════════════════════════════════════════════
    
    if _is_pagination_command(text):
        _append_to_history(session, "user", text)
        
        # Get current search state
        current_query = session.extracted_attributes.get("_search_term", "")
        shown_ids = session.extracted_attributes.get("_shown_ids", [])
        offset = session.extracted_attributes.get("_offset", 0)
        
        if not current_query:
            response_text = "What would you like me to show more of? Try searching for a product first."
            _append_to_history(session, "agent", response_text)
            return {"type": "question", "text": response_text, "options": None, "products": None, "metadata": _build_metadata(session)}
        
        # Re-search with increased offset
        max_price = session.extracted_attributes.get("_max_price")
        new_offset = offset + 3  # Skip the first N already shown
        session.extracted_attributes["_offset"] = new_offset
        
        products_data = search_and_recommend(current_query, session.extracted_attributes, max_price=max_price)
        
        # Filter out already-shown products
        unseen = [p for p in products_data if p.get("productId") not in shown_ids]
        
        if unseen:
            # Track shown IDs
            for p in unseen[:3]:
                shown_ids.append(p.get("productId"))
            session.extracted_attributes["_shown_ids"] = shown_ids
            
            # Save last product for cart
            if unseen:
                session.extracted_attributes["_last_product"] = {
                    "title": unseen[0].get("title", ""),
                    "price": unseen[0].get("price", 0),
                    "brand": unseen[0].get("brand", ""),
                }
            
            response_text = f"Here are more {current_query} options:"
            _append_to_history(session, "agent", response_text)
            return {"type": "recommendations", "text": response_text, "options": None, "products": unseen[:3], "metadata": _build_metadata(session)}
        else:
            response_text = f"You've seen all available options for {current_query}. Would you like to try different filters or search for something else?"
            _append_to_history(session, "agent", response_text)
            return {"type": "question", "text": response_text, "options": ["Try different filters", "New search"], "products": None, "metadata": _build_metadata(session)}

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 1: DETERMINE IF THIS IS A NEW SEARCH OR A REFINEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    
    is_refinement = _is_refinement(text)
    prev_intent = session.extracted_attributes.get("_search_term", "")
    
    # DEBUG LOG
    logger.info(f"[INTENT] Previous Intent: '{prev_intent}' | Detected Refinement: {is_refinement} | Raw: '{text}'")
    
    if not is_refinement:
        # NEW INTENT — wipe previous product context completely
        # BUT preserve the cart across searches!
        preserved_cart = session.extracted_attributes.get("_cart", [])
        session.extracted_attributes = {"_cart": preserved_cart}
        session.confidence_score = 0.0
        session.question_count = 0

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 2: EXTRACT INTENT FROM RAW QUERY
    # ═══════════════════════════════════════════════════════════════════════════
    
    raw_query = text.strip()
    
    # Clean filler words for search but keep original for display
    search_query = _clean_query_for_search(raw_query)
    
    # Gender/audience-aware search enhancement
    search_query = _enhance_query_with_context(search_query)
    
    # Check if this is a greeting/generic message (not a product query)
    if _is_greeting(raw_query):
        _append_to_history(session, "user", text)
        response_text = "I'd be happy to help! What are you looking for today?"
        _append_to_history(session, "agent", response_text)
        return {
            "type": "question",
            "text": response_text,
            "options": None,
            "products": None,
            "metadata": _build_metadata(session),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 2.5: GIBBERISH / UNRECOGNIZABLE INPUT DETECTION
    # ═══════════════════════════════════════════════════════════════════════════
    
    # If cleaned query is very short, has no vowels, or is purely alphanumeric noise
    _cleaned_lower = search_query.lower().strip()
    _has_vowel = any(v in _cleaned_lower for v in "aeiou")
    _is_too_short = len(_cleaned_lower) <= 2 and not _cleaned_lower.isdigit()
    # Check consonant-to-vowel ratio (gibberish has very high ratio)
    _vowels = sum(1 for c in _cleaned_lower if c in "aeiou")
    _consonants = sum(1 for c in _cleaned_lower if c.isalpha() and c not in "aeiou")
    _ratio = _consonants / max(_vowels, 1)
    # Whitelist of legitimate short product words that have high consonant ratios
    _product_whitelist = {
        "shirt", "shirts", "t-shirt", "t-shirts", "tshirt", "tshirts",
        "pants", "shorts", "socks", "gloves", "scarf", "watch", "watches",
        "boots", "skirts", "skirt", "dress", "dresses", "kurts", "kurta",
        "gym", "dry", "fly", "try", "cry", "fry", "sky", "sync",
        "ctrl", "btn", "rgb", "hdmi", "usb", "wifi", "png", "jpg",
        "whey", "bcaa", "crm", "erp", "sdk", "api",
    }
    # Check if any word in the query is a whitelisted product term
    _query_words = set(_cleaned_lower.replace("-", " ").split())
    _in_whitelist = bool(_query_words & _product_whitelist)
    
    _is_random = (
        not _in_whitelist and (
            (_is_too_short and not _is_greeting(raw_query)) or
            (len(_cleaned_lower) >= 3 and not _has_vowel and _cleaned_lower.isalpha()) or
            (len(_cleaned_lower) >= 5 and _ratio > 5 and not _in_whitelist) or
            (re.match(r'^\d+[a-z]+$', _cleaned_lower) and len(_cleaned_lower) >= 5) or
            (re.match(r'^[a-z]+\d+[a-z]*$', _cleaned_lower) and len(_cleaned_lower) >= 5)
        )
    )
    
    if _is_random:
        _append_to_history(session, "user", text)
        response_text = (
            "I couldn't recognize that as a product. If it's a product code or abbreviation, "
            "could you please specify what you're looking for? For example: \"Nike shoes\" or \"wireless earbuds\"."
        )
        _append_to_history(session, "agent", response_text)
        return {
            "type": "question",
            "text": response_text,
            "options": ["Show categories", "Continue shopping"],
            "products": None,
            "metadata": _build_metadata(session),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 3: CLASSIFY INTENT (for smart responses, NOT for search)
    # ═══════════════════════════════════════════════════════════════════════════
    
    classification = classify(search_query)
    
    # Check for ambiguity — only ask if genuinely ambiguous
    if classification.isAmbiguous and classification.clarificationOptions:
        _append_to_history(session, "user", text)
        response_text = f"Did you mean:"
        _append_to_history(session, "agent", response_text)
        return {
            "type": "question",
            "text": response_text,
            "options": classification.clarificationOptions,
            "products": None,
            "metadata": _build_metadata(session),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 4: HANDLE REFINEMENTS (price, color, brand, size, gender, sorting)
    # ═══════════════════════════════════════════════════════════════════════════
    
    if is_refinement:
        # Extract constraints from the refinement message
        constraints = _extract_constraints(raw_query)
        session.extracted_attributes.update(constraints)
        
        # Use previous search term as the base
        prev_type = session.extracted_attributes.get("_search_term", "")
        if prev_type:
            search_query = prev_type
            # Apply gender/audience modifier to search
            gender_words = {"women", "woman", "men", "man", "boys", "girls", "kids", "baby"}
            text_words = set(text.lower().split())
            gender_match = gender_words & text_words
            if gender_match:
                gender = list(gender_match)[0]
                if gender not in search_query:
                    search_query = f"{gender} {search_query}"
            # Apply brand to search if specified
            if constraints.get("brand"):
                if constraints["brand"].lower() not in search_query.lower():
                    search_query = f"{constraints['brand']} {search_query}"
            # Apply color to search
            if constraints.get("color"):
                if constraints["color"].lower() not in search_query.lower():
                    search_query = f"{constraints['color']} {search_query}"
        
        # Extract price from refinement for max_price
        refinement_price = _extract_price_from_query(raw_query)
        if refinement_price:
            session.extracted_attributes["_max_price"] = refinement_price
        
        # Extract min price from refinement (above X)
        refinement_min_price = _extract_min_price_from_query(raw_query)
        if refinement_min_price:
            session.extracted_attributes["_min_price"] = refinement_min_price
        
        logger.info(f"[INTENT] Refinement applied. New query: '{search_query}' | Constraints: {constraints}")

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP 5: SEARCH AND RETURN PRODUCTS
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Store the search term for potential refinements
    if not is_refinement:
        session.extracted_attributes["_search_term"] = search_query
    
    # Extract price constraint — from current query OR from session (refinement)
    max_price = _extract_price_from_query(raw_query)
    if not max_price and is_refinement:
        max_price = session.extracted_attributes.get("_max_price")
    
    # Also check for "above X" (min price)
    min_price = _extract_min_price_from_query(raw_query)
    if not min_price and is_refinement:
        min_price = session.extracted_attributes.get("_min_price")
    if min_price:
        session.extracted_attributes["_min_price"] = min_price
    
    # DEBUG LOG
    logger.info(f"[INTENT] Final Query: '{search_query}' | max_price={max_price} | min_price={min_price} | refinement={is_refinement}")
    
    # Add user message to history
    _append_to_history(session, "user", text)
    
    # Check if this is a brand-only query (needs clarification)
    from services.product_catalog import _extract_brand_from_query, _extract_product_term
    brand = _extract_brand_from_query(search_query)
    product_term = _extract_product_term(search_query, brand)
    
    if brand and not product_term:
        # Brand-only query — ask for clarification
        response_text = f"Which {brand.title()} product are you looking for?"
        options = None
        # Suggest common product types for this brand
        if brand in ["adidas", "nike", "puma", "reebok"]:
            options = ["Sneakers", "Slides", "Track Pants", "T-Shirts", "Socks"]
        elif brand in ["apple"]:
            options = ["iPhone", "MacBook", "iPad", "AirPods", "Apple Watch"]
        elif brand in ["samsung"]:
            options = ["Phones", "Earbuds", "Tablets", "Smartwatch"]
        elif brand in ["boat"]:
            options = ["Earbuds", "Headphones", "Speakers", "Smartwatch"]
        else:
            options = ["Shoes", "Clothing", "Accessories", "Electronics"]
        
        _append_to_history(session, "agent", response_text)
        return {
            "type": "question",
            "text": response_text,
            "options": options,
            "products": None,
            "metadata": _build_metadata(session),
        }
    
    # SEARCH using the user's actual words
    products_data = search_and_recommend(
        search_query,
        session.extracted_attributes,
        max_price=max_price,
    )
    
    # ═══ RETRIEVAL SAFETY CHECK ═══
    # If search returned None, it means Tier 4 rejected the query as sentence-like.
    # Ask clarification instead of showing fake products.
    if products_data is None:
        _append_to_history(session, "user", text)
        # Detect context to give a useful clarification question
        _tl = text.lower()
        if any(w in _tl for w in ["sunny", "rainy", "weather", "cold", "hot", "warm"]):
            _opts = ["Outdoor essentials", "Clothing & fashion", "Sunscreen & skincare", "Umbrellas & rain gear"]
            _clarify = "It sounds like you're asking about weather-related needs. What are you looking for?"
        elif any(w in _tl for w in ["hungry", "eat", "food", "meal", "snack"]):
            _opts = ["Snacks", "Ready-to-eat meals", "Cooking ingredients", "Beverages"]
            _clarify = "Sounds like you want something to eat! What kind of food are you looking for?"
        elif any(w in _tl for w in ["bored", "fun", "entertain", "relax"]):
            _opts = ["Games & toys", "Books", "Music & audio", "Hobby supplies"]
            _clarify = "Looking for something fun? What kind of entertainment interests you?"
        elif any(w in _tl for w in ["bought", "have", "got", "own"]):
            _opts = ["Accessories for it", "Essentials to go with it", "Upgrades", "Maintenance items"]
            _clarify = "Would you like recommendations to go with your recent purchase?"
        else:
            _opts = ["Electronics", "Fashion & clothing", "Grocery & food", "Home & kitchen", "Health & beauty"]
            _clarify = "I'd love to help! Could you be a bit more specific about what you're looking for?"
        _append_to_history(session, "agent", _clarify)
        return {
            "type": "question",
            "text": _clarify,
            "options": _opts,
            "products": None,
            "metadata": _build_metadata(session),
        }
    
    # Handle price filter exclusion
    if products_data and len(products_data) == 1 and isinstance(products_data[0], dict) and products_data[0].get("_filter_note"):
        filter_info = products_data[0]
        all_products = filter_info.get("_all_products", [])
        mp = filter_info.get("_max_price", 0)
        
        if all_products:
            cheapest = min(all_products, key=lambda p: p.get("price", 99999))
            response_text = (
                f"I couldn't find {search_query} under ₹{int(mp)}. "
                f"The closest starts at ₹{int(cheapest.get('price', 0))}. "
                f"Here's what's available:"
            )
        else:
            response_text = f"No exact matches for that budget. Here are the closest options:"
        
        _append_to_history(session, "agent", response_text)
        return {
            "type": "recommendations",
            "text": response_text,
            "options": None,
            "products": all_products[:3],
            "metadata": _build_metadata(session),
        }
    
    # Build response
    if products_data:
        product_name = classification.subCategory if classification.confidence > 0.5 else search_query
        response_text = f"Here are the best {product_name} options I found for you!"
    else:
        # This should never happen (search_and_recommend always returns something)
        response_text = f"I couldn't find exact matches for \"{search_query}\". Try a different search term or check the spelling."
        _append_to_history(session, "agent", response_text)
        return {
            "type": "question",
            "text": response_text,
            "options": ["Try different filters", "New search"],
            "products": None,
            "metadata": _build_metadata(session),
        }
    
    _append_to_history(session, "agent", response_text)
    
    # Save the first product for "add to cart" tracking + track shown IDs for pagination
    if products_data:
        first_product = products_data[0]
        session.extracted_attributes["_last_product"] = {
            "title": first_product.get("title", ""),
            "price": first_product.get("price", 0),
            "brand": first_product.get("brand", ""),
        }
        # Track shown product IDs (for "more" pagination)
        shown_ids = session.extracted_attributes.get("_shown_ids", [])
        for p in products_data[:5]:
            pid = p.get("productId")
            if pid and pid not in shown_ids:
                shown_ids.append(pid)
        session.extracted_attributes["_shown_ids"] = shown_ids
        session.extracted_attributes["_offset"] = len(shown_ids)
    
    return {
        "type": "recommendations",
        "text": response_text,
        "options": None,
        "products": products_data[:5],
        "metadata": _build_metadata(session),
    }


def _parse_bedrock_response(raw_response: str) -> dict[str, Any]:
    """Parse Bedrock's raw text response into structured data.

    Expects JSON with: extracted_attributes, response_text, options.
    Falls back gracefully if JSON parsing fails.

    Args:
        raw_response: Raw text from Bedrock.

    Returns:
        Parsed dict with extracted_attributes, response_text, and options.
    """
    try:
        # Try direct JSON parse first
        parsed = json.loads(raw_response)
        if isinstance(parsed, dict):
            return {
                "extracted_attributes": parsed.get("extracted_attributes", {}),
                "response_text": parsed.get("response_text", ""),
                "options": parsed.get("options"),
            }
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code blocks or embedded JSON
    try:
        # Look for JSON within code fences
        import re

        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(1))
            if isinstance(parsed, dict):
                return {
                    "extracted_attributes": parsed.get("extracted_attributes", {}),
                    "response_text": parsed.get("response_text", ""),
                    "options": parsed.get("options"),
                }

        # Look for JSON object anywhere in the response
        brace_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if brace_match:
            parsed = json.loads(brace_match.group(0))
            if isinstance(parsed, dict):
                return {
                    "extracted_attributes": parsed.get("extracted_attributes", {}),
                    "response_text": parsed.get("response_text", ""),
                    "options": parsed.get("options"),
                }
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback: treat entire response as response text with no attributes
    logger.warning(
        "Could not parse Bedrock response as JSON, using raw text as response",
        extra={"raw_response_preview": raw_response[:200]},
    )
    return {
        "extracted_attributes": {},
        "response_text": raw_response.strip()[:300],  # Truncate if too long
        "options": None,
    }


def _handle_no_extract_tracking(
    session: Session, extracted_attrs: dict
) -> tuple[dict, bool]:
    """Track consecutive no-extraction attempts.

    If no meaningful attributes are extracted for 3 consecutive messages,
    signals that the category list should be shown.

    Args:
        session: Current session state.
        extracted_attrs: Attributes extracted from the latest message.

    Returns:
        Tuple of (updated_attrs, show_categories_flag).
    """
    # Filter out empty/None values to determine if anything was truly extracted
    meaningful_attrs = {
        k: v
        for k, v in extracted_attrs.items()
        if v is not None and v != "" and k != _NO_EXTRACT_COUNT_KEY
    }

    current_count = session.extracted_attributes.get(_NO_EXTRACT_COUNT_KEY, 0)

    if not meaningful_attrs:
        # No new attributes extracted — increment counter
        new_count = current_count + 1
        if new_count >= _MAX_NO_EXTRACT_ATTEMPTS:
            # Reset counter and signal category fallback
            session.extracted_attributes[_NO_EXTRACT_COUNT_KEY] = 0
            return extracted_attrs, True
        else:
            session.extracted_attributes[_NO_EXTRACT_COUNT_KEY] = new_count
            return extracted_attrs, False
    else:
        # Attributes were extracted — reset counter
        session.extracted_attributes[_NO_EXTRACT_COUNT_KEY] = 0
        return extracted_attrs, False


def _build_category_fallback_response(session: Session, user_text: str) -> dict:
    """Build a response showing available categories after repeated no-extraction.

    Args:
        session: Current session state.
        user_text: The user's latest message.

    Returns:
        Response dict with category options.
    """
    _append_to_history(session, "user", user_text)

    response_text = (
        "I'd love to help! Here are the categories I can assist with. "
        "Which one interests you?"
    )

    _append_to_history(session, "agent", response_text)

    return {
        "type": "question",
        "text": response_text,
        "options": _AVAILABLE_CATEGORIES,
        "products": None,
        "metadata": {
            "confidenceScore": session.confidence_score,
            "extractedAttributes": {
                k: v
                for k, v in session.extracted_attributes.items()
                if k != _NO_EXTRACT_COUNT_KEY
            },
            "questionCount": session.question_count,
        },
    }


def _build_recommendation_response(session: Session, bedrock_text: str, user_query: str = "") -> dict:
    """Build a recommendations response using Rainforest API (cached) + local catalog.

    Args:
        session: Current session with extracted attributes.
        bedrock_text: Response text generated by Bedrock.
        user_query: The original user message (used for more specific searches).

    Returns:
        Response dict with product recommendations.
    """
    from services.product_catalog import search_and_recommend

    # Filter out internal tracking keys for catalog query
    query_attrs = {
        k: v
        for k, v in session.extracted_attributes.items()
        if k != _NO_EXTRACT_COUNT_KEY and v is not None and v != "" and not k.startswith("_")
    }

    # Build a SMART search term — use the most specific info available
    search_parts = []
    if query_attrs.get("color") and query_attrs["color"] != "_no_preference":
        search_parts.append(query_attrs["color"])
    if query_attrs.get("brand") and query_attrs["brand"] != "_no_preference":
        search_parts.append(query_attrs["brand"])
    if query_attrs.get("type"):
        search_parts.append(query_attrs["type"])
    elif query_attrs.get("subcategory"):
        search_parts.append(query_attrs["subcategory"])
    elif query_attrs.get("category"):
        search_parts.append(query_attrs["category"])

    search_term = " ".join(search_parts) if search_parts else ""

    # If the user's original query is more specific, prefer it
    # e.g., "puma sneakers" is better than just "sneakers"
    if user_query and len(user_query.strip()) > len(search_term):
        # Remove common filler words
        clean_query = user_query.lower().strip()
        for filler in ["i want", "i need", "get me", "find me", "show me", "looking for", "under", "with good rating", "if its available", "please"]:
            clean_query = clean_query.replace(filler, "")
        clean_query = " ".join(clean_query.split())  # collapse spaces
        if len(clean_query) > 3 and len(clean_query) > len(search_term):
            search_term = clean_query

    if not search_term:
        search_term = query_attrs.get("category", "products")

    # Use the hybrid search (Rainforest API with cache → local fallback)
    products_data = search_and_recommend(search_term, query_attrs)

    # Handle price/rating filter exclusion — intelligent "no match in range" response
    if products_data and len(products_data) == 1 and isinstance(products_data[0], dict) and products_data[0].get("_filter_note") == "no_match_in_range":
        filter_info = products_data[0]
        all_products = filter_info.get("_all_products", [])
        max_price = filter_info.get("_max_price")
        min_rating = filter_info.get("_min_rating")
        
        # Build an intelligent response
        if max_price and all_products:
            cheapest = min(all_products, key=lambda p: p.get("price", 99999))
            cheapest_price = cheapest.get("price", 0)
            response_text = (
                f"I couldn't find highly-rated {search_term} under ₹{int(max_price)}. "
                f"The closest option starts at ₹{int(cheapest_price)}. "
                f"Would you like to see what's available at a slightly higher budget?"
            )
            # Show the products anyway with a note
            return {
                "type": "recommendations",
                "text": response_text,
                "options": [f"Show under ₹{int(cheapest_price + 500)}", "Try a different product"],
                "products": all_products[:3],
                "metadata": {
                    "confidenceScore": session.confidence_score,
                    "extractedAttributes": query_attrs,
                    "questionCount": session.question_count,
                },
            }
        else:
            response_text = f"There are no products matching that exact criteria. Here are the closest options I found:"
            return {
                "type": "recommendations",
                "text": response_text,
                "options": None,
                "products": all_products[:3],
                "metadata": {
                    "confidenceScore": session.confidence_score,
                    "extractedAttributes": query_attrs,
                    "questionCount": session.question_count,
                },
            }

    # search_and_recommend never returns empty (has fallback), but just in case
    if not products_data:
        response_text = "I couldn't find exact matches. Try a different search term!"
        return {
            "type": "question",
            "text": response_text,
            "options": ["New search"],
            "products": None,
            "metadata": {
                "confidenceScore": session.confidence_score,
                "extractedAttributes": query_attrs,
                "questionCount": session.question_count,
            },
        }

    # Use Bedrock text if meaningful, otherwise generate explanation
    if bedrock_text and len(bedrock_text) > 10:
        response_text = bedrock_text
    else:
        response_text = _generate_recommendation_explanation(query_attrs)

    return {
        "type": "recommendations",
        "text": response_text,
        "options": None,
        "products": products_data,
        "metadata": {
            "confidenceScore": session.confidence_score,
            "extractedAttributes": query_attrs,
            "questionCount": session.question_count,
        },
    }


def _build_question_response(
    session: Session, response_text: str, options: list[str] | None
) -> dict:
    """Build a question response.

    Args:
        session: Current session state.
        response_text: Question text generated by Bedrock.
        options: Optional quick reply options.

    Returns:
        Response dict for a question.
    """
    # Sanitize options: max 5 items
    if options and len(options) > 5:
        options = options[:5]

    return {
        "type": "question",
        "text": response_text,
        "options": options,
        "products": None,
        "metadata": {
            "confidenceScore": session.confidence_score,
            "extractedAttributes": {
                k: v
                for k, v in session.extracted_attributes.items()
                if k != _NO_EXTRACT_COUNT_KEY
            },
            "questionCount": session.question_count,
        },
    }


def _generate_recommendation_explanation(attributes: dict) -> str:
    """Generate a short explanation of why these products were recommended.

    Args:
        attributes: The known attributes used for filtering.

    Returns:
        A concise explanation string (max 2 sentences).
    """
    parts = []
    if "category" in attributes:
        parts.append(attributes["category"])
    if "brand" in attributes:
        parts.append(attributes["brand"])
    if "type" in attributes or "subcategory" in attributes:
        parts.append(attributes.get("type") or attributes.get("subcategory", ""))
    if "priceRange" in attributes:
        parts.append(f"in the {attributes['priceRange']} price range")

    if parts:
        description = " ".join(parts).strip()
        return f"Here are my top picks based on your preference for {description}!"

    return "Here are my top recommendations based on what you've told me!"


def _append_to_history(session: Session, role: str, text: str) -> None:
    """Append a message to the session conversation history.

    Respects the 50-message limit by trimming oldest messages if needed.

    Args:
        session: The session to update.
        role: Message role ('user' or 'agent').
        text: Message text content.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    message = ConversationMessage(role=role, text=text, timestamp=now)

    # Enforce 50-message limit
    if len(session.conversation_history) >= 50:
        session.conversation_history = session.conversation_history[-49:]

    session.conversation_history.append(message)
