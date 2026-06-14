"""Amazon Bedrock client for IntentFlow NLU integration."""

import json
import logging
import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from config import settings

logger = logging.getLogger(__name__)

# Local mode flag for hackathon development without Bedrock access
USE_LOCAL_BEDROCK = os.getenv("USE_LOCAL_BEDROCK", "false").lower() == "true"


class AgentProcessingError(Exception):
    """Raised when Bedrock invocation fails after retries.

    Contains a user-friendly message suitable for returning to the client.
    """

    def __init__(
        self,
        message: str = "I'm having trouble processing your request right now. Please try again in a moment.",
    ):
        super().__init__(message)
        self.user_message = message


def _has_enough_info(known_attrs: dict, extracted: dict, category: str | None, brand: str | None) -> bool:
    """Check if we have enough info to recommend products directly.
    
    PHILOSOPHY: If the user has expressed a clear product intent (we know WHAT they want),
    go straight to recommendations. Don't ask unnecessary questions.
    
    Returns True if:
    - We have a product type identified (the user said what they want)
    - OR we have category + brand
    - OR we have category + any 2 specific attributes
    """
    all_attrs = {**known_attrs, **extracted}
    has_category = bool(category)
    has_product_type = bool(all_attrs.get("type") or all_attrs.get("subcategory"))
    has_brand = bool(brand and brand != "_no_preference")
    has_price = bool(all_attrs.get("priceRange"))
    has_color = bool(all_attrs.get("color"))
    has_size = bool(all_attrs.get("size"))
    
    # KEY INSIGHT: If we know WHAT they want (product type), that's enough to search
    if has_product_type:
        return True
    # If we have category + brand, that's enough
    if has_category and has_brand:
        return True
    # If we have category + any 2 attributes
    extras = sum([has_brand, has_price, has_color, has_size])
    if has_category and extras >= 2:
        return True
    return False


def _get_mock_response(prompt: str) -> str:
    """Return a context-aware mock response using the OntologyEngine.

    Used when USE_LOCAL_BEDROCK=true to enable development without AWS credentials.
    Parses the user message from the prompt, classifies using the ontology,
    extracts attributes intelligently, and recommends popular brands.
    """
    import re

    from services.ontology_engine import classify, get_popular_brands, get_all_top_categories

    # Extract the user message from the prompt
    user_msg = ""
    match = re.search(r"NEW USER MESSAGE:\s*(.+?)(?:\n\n|\nINSTRUCTIONS:)", prompt, re.DOTALL)
    if match:
        user_msg = match.group(1).strip().lower()

    # Extract known attributes from the prompt
    known_attrs = {}
    attrs_match = re.search(r"CURRENTLY KNOWN ATTRIBUTES:\s*(\{.*?\})", prompt, re.DOTALL)
    if attrs_match:
        try:
            known_attrs = json.loads(attrs_match.group(1))
        except json.JSONDecodeError:
            pass

    # ─── Mock order history (simulated past purchases for personalization) ─────
    ORDER_HISTORY = [
        {"product": "Levi's 511 Slim Fit Jeans", "category": "Fashion", "brand": "Levi's"},
        {"product": "Sony WH-1000XM5 Headphones", "category": "Electronics", "brand": "Sony"},
        {"product": "Maggi 2-Minute Noodles Pack of 12", "category": "Grocery", "brand": "Maggi"},
        {"product": "Dettol Antiseptic Liquid 1L", "category": "Essentials", "brand": "Dettol"},
        {"product": "Nike Air Zoom Pegasus 40", "category": "Fashion", "brand": "Nike"},
        {"product": "Tata Tea Gold 1kg", "category": "Grocery", "brand": "Tata"},
        {"product": "boAt Rockerz 450 Headphones", "category": "Electronics", "brand": "boAt"},
        {"product": "Boldfit Dumbbell Set", "category": "Sports & Fitness", "brand": "Boldfit"},
        {"product": "Pampers Diapers L Size", "category": "Baby Products", "brand": "Pampers"},
    ]

    # ─── Brand detection (expanded for all categories) ────────────────────────
    brand_keywords = {
        "Nike": ["nike"], "Adidas": ["adidas"], "Puma": ["puma"], "Converse": ["converse"],
        "Levi's": ["levi", "levis", "levi's"], "Biba": ["biba"], "Woodland": ["woodland"],
        "Allen Solly": ["allen solly"], "Van Heusen": ["van heusen"], "H&M": ["h&m", "hm"],
        "Maggi": ["maggi"], "Tata": ["tata"], "Amul": ["amul"], "Nescafe": ["nescafe"],
        "Haldiram's": ["haldiram"], "Aashirvaad": ["aashirvaad"], "Fortune": ["fortune"],
        "Daawat": ["daawat"], "Saffola": ["saffola"],
        "Bosch": ["bosch"], "Stanley": ["stanley"], "Dewalt": ["dewalt"], "Makita": ["makita"],
        "Black+Decker": ["black+decker", "black and decker"],
        "Sony": ["sony"], "Samsung": ["samsung"], "Apple": ["apple"], "JBL": ["jbl"],
        "boAt": ["boat"], "OnePlus": ["oneplus"], "Xiaomi": ["xiaomi", "redmi"],
        "Dettol": ["dettol"], "Colgate": ["colgate"], "Dove": ["dove"], "Nivea": ["nivea"],
        "Sensodyne": ["sensodyne"], "Surf Excel": ["surf excel", "surf"],
        "Prestige": ["prestige"], "Hawkins": ["hawkins"], "Pigeon": ["pigeon"],
        "Milton": ["milton"], "Philips": ["philips"], "Bajaj": ["bajaj"],
        "LEGO": ["lego"], "Funskool": ["funskool"], "Hasbro": ["hasbro"],
        "Pedigree": ["pedigree"], "Royal Canin": ["royal canin"], "Drools": ["drools"],
        "Maybelline": ["maybelline"], "Lakme": ["lakme"], "L'Oreal": ["loreal", "l'oreal"],
        "Studds": ["studds"], "Steelbird": ["steelbird"],
        "Pampers": ["pampers"], "Huggies": ["huggies"], "MamyPoko": ["mamypoko"],
        "Omron": ["omron"], "MuscleBlaze": ["muscleblaze"], "Optimum Nutrition": ["optimum nutrition", "on whey"],
        "Boldfit": ["boldfit"], "Decathlon": ["decathlon"],
        "HP": ["hp"], "Dell": ["dell"], "Lenovo": ["lenovo"], "ASUS": ["asus"],
        "Canon": ["canon"], "Nikon": ["nikon"], "GoPro": ["gopro"],
        "Parker": ["parker"], "Casio": ["casio"], "Titan": ["titan"], "Fastrack": ["fastrack"],
        "MDH": ["mdh"], "Everest": ["everest"],
        "Penguin": ["penguin"], "Arihant": ["arihant"],
    }

    # ─── Natural Language Multi-Attribute Extraction ──────────────────────────
    # Handle complex queries like "black shoes with good rating under 3000"
    # Extract color, quality preferences, price — all in one go

    extracted = {}
    response_text = ""
    options = None

    # Detect quality/rating preferences
    if any(w in user_msg for w in ["good rating", "best rated", "top rated", "highly rated", "popular", "best seller", "best selling", "trending"]):
        extracted["_prefer_high_rating"] = True

    # Detect urgency / quick delivery preferences
    if any(w in user_msg for w in ["quick", "fast delivery", "same day", "urgent", "asap", "prime"]):
        extracted["_prefer_prime"] = True

    # ─── Attribute extraction using OntologyEngine ────────────────────────────

    # Use ontology engine for classification
    context = {"category": known_attrs.get("category")} if known_attrs.get("category") else None
    classification = classify(user_msg, context=context)

    # If ontology classified the product, extract structured attributes
    if classification and classification.confidence > 0:
        if classification.isAmbiguous:
            # Return clarification question
            response_text = f"I found a few options for \"{user_msg}\". Which one are you looking for?"
            options = classification.clarificationOptions
            mock_response = {
                "extracted_attributes": {},
                "response_text": response_text,
                "options": options,
            }
            return json.dumps(mock_response)

        # Map classification to extracted attributes
        if not known_attrs.get("category"):
            extracted["category"] = classification.topCategory
        if classification.subCategory:
            extracted["subcategory"] = classification.subCategory
        extracted["type"] = classification.normalizedProduct

    # Detect brand from user message
    for brand, keywords in brand_keywords.items():
        if any(kw in user_msg for kw in keywords):
            extracted["brand"] = brand
            break

    # Handle "no preference" / "any" / "doesn't matter"
    if any(phrase in user_msg for phrase in ["no preference", "any", "doesn't matter", "don't care", "whatever", "recommend", "best"]):
        if not known_attrs.get("brand") and not extracted.get("brand"):
            extracted["brand"] = "_no_preference"

    # Detect price from option clicks and natural language
    price_patterns = [
        (r"under\s*(?:rs\.?|₹|inr)?\s*(\d+)", lambda m: f"0-{m.group(1)}"),
        (r"(?:rs\.?|₹|inr)\s*(\d+)\s*(?:to|-)\s*(?:rs\.?|₹|inr)?\s*(\d+)", lambda m: f"{m.group(1)}-{m.group(2)}"),
        (r"(?:below|less than|within|max|budget)\s*(?:rs\.?|₹|inr)?\s*(\d+)", lambda m: f"0-{m.group(1)}"),
        (r"(?:rs\.?|₹|inr)\s*(\d+)", lambda m: f"0-{m.group(1)}"),
    ]
    for pattern, formatter in price_patterns:
        price_match = re.search(pattern, user_msg)
        if price_match:
            extracted["priceRange"] = formatter(price_match)
            break

    # Handle price option clicks like "Under ₹500"
    if "under" in user_msg and "₹" in user_msg:
        amt_match = re.search(r"₹(\d+)", user_msg)
        if amt_match:
            extracted["priceRange"] = f"0-{amt_match.group(1)}"

    # Detect size
    size_match = re.search(r"\bsize\s+(\w+)\b", user_msg)
    if size_match:
        extracted["size"] = size_match.group(1).upper()
    # Numeric sizes for shoes
    detected_subcat = known_attrs.get("subcategory") or extracted.get("subcategory") or known_attrs.get("type") or extracted.get("type")
    shoe_size_match = re.search(r"\b(6|7|8|9|10|11|12)\b", user_msg)
    if shoe_size_match and detected_subcat and detected_subcat.lower() in ("shoes", "sneakers", "boots", "footwear"):
        extracted["size"] = shoe_size_match.group(1)

    # Detect color
    colors = ["black", "white", "red", "blue", "green", "grey", "gray", "brown", "navy", "khaki", "indigo", "purple", "orange", "yellow", "silver", "teal", "olive", "pink", "beige", "maroon"]
    for color in colors:
        if color in user_msg:
            extracted["color"] = color.capitalize()
            break

    # ─── Generate contextual response using ontology ──────────────────────────

    current_category = extracted.get("category") or known_attrs.get("category")
    current_subcat = extracted.get("subcategory") or known_attrs.get("subcategory") or extracted.get("type") or known_attrs.get("type")
    current_brand = extracted.get("brand") or known_attrs.get("brand")
    product_key = extracted.get("type") or known_attrs.get("type")

    # Get brands from ontology for the classified product
    ontology_brands = []
    if product_key:
        ontology_brands = get_popular_brands(product_key)

    # Check order history for personalization
    history_brands_for_category = [
        o["brand"] for o in ORDER_HISTORY
        if o["category"] == current_category
    ]

    if not current_category and not product_key:
        # No ontology match — but the user typed SOMETHING.
        # Treat their message as a direct product search.
        # Only ask "what are you looking for" if the message is very generic/greeting.
        generic_messages = ["hi", "hello", "hey", "help", "start", "yes", "no", "ok", "okay", "thanks", "thank you"]
        if user_msg.strip() in generic_messages or len(user_msg.strip()) < 3:
            response_text = "I'd be happy to help! What are you looking for today?"
            options = None
        else:
            # User said a specific product — go straight to search
            # Use their exact words as the search/product type
            extracted["type"] = user_msg.strip()
            extracted["category"] = "General"
            product_desc = user_msg.strip()
            response_text = f"Got it! Let me find the best {product_desc} options for you."
            options = None
    elif classification and classification.isAmbiguous:
        # Genuinely ambiguous — ask ONE clarifying question
        response_text = f"I found a few options for \"{user_msg}\". Which one did you mean?"
        options = classification.clarificationOptions
    elif _has_enough_info(known_attrs, extracted, current_category, current_brand):
        # We have enough info — go straight to recommendations
        product_desc = f"{current_brand or ''} {current_subcat or current_category}".strip()
        if extracted.get("color"):
            product_desc = f"{extracted['color']} {product_desc}"
        response_text = f"Got it! Let me find the best {product_desc} options for you."
        options = None
    elif not current_brand or current_brand == "_no_preference":
        # Suggest popular brands dynamically from ontology
        if current_brand == "_no_preference":
            extracted.pop("brand", None)

        popular = ontology_brands if ontology_brands else []

        # Personalize: put previously ordered brands first
        if history_brands_for_category:
            personalized = []
            for hb in history_brands_for_category:
                if hb not in personalized:
                    personalized.append(hb)
            for pb in popular:
                if pb not in personalized:
                    personalized.append(pb)
            popular = personalized[:5]

        if popular:
            product_name = current_subcat or current_category.lower()
            if history_brands_for_category:
                response_text = f"Based on your past orders, I'd suggest {history_brands_for_category[0]} for {product_name}. Or pick another brand!"
            else:
                response_text = f"For {product_name}, these are the most popular brands. Any preference?"
            options = popular[:4] + ["No preference"]
        else:
            response_text = "Any brand preference?"
            options = ["No preference"]

    elif not known_attrs.get("priceRange") and not extracted.get("priceRange"):
        product_name = current_subcat or current_category.lower()
        # Use ontology price ranges if available
        price_ranges = {} if product_key else {}
        if price_ranges:
            budget_max = price_ranges.get("budget", "1000").split("-")[-1]
            mid_max = price_ranges.get("mid", "3000").split("-")[-1]
            premium_max = price_ranges.get("premium", "10000").split("-")[-1]
            response_text = f"What's your budget for the {product_name}?"
            options = [f"Under ₹{budget_max}", f"Under ₹{mid_max}", f"Under ₹{premium_max}", "No limit"]
        else:
            response_text = f"What's your budget for the {product_name}?"
            if current_category == "Grocery":
                options = ["Under ₹200", "Under ₹500", "Under ₹1000", "No limit"]
            elif current_category == "Essentials":
                options = ["Under ₹200", "Under ₹500", "No limit"]
            elif current_category == "Fashion":
                options = ["Under ₹1000", "Under ₹2000", "Under ₹3000", "Under ₹5000"]
            elif current_category == "Electronics":
                options = ["Under ₹5000", "Under ₹10000", "Under ₹20000", "Under ₹50000"]
            elif current_category == "Sports & Fitness":
                options = ["Under ₹1000", "Under ₹3000", "Under ₹5000", "Under ₹10000"]
            else:
                options = ["Under ₹1000", "Under ₹3000", "Under ₹5000", "No limit"]

    elif not known_attrs.get("size") and not extracted.get("size") and current_category == "Fashion" and current_subcat and current_subcat.lower() in ("shoes", "sneakers", "boots", "footwear"):
        response_text = "What size do you need?"
        options = ["7", "8", "9", "10", "11"]

    elif not known_attrs.get("size") and not extracted.get("size") and current_category == "Fashion" and current_subcat and current_subcat.lower() in ("t-shirts", "shirts", "kurta", "ethnic wear", "jackets"):
        response_text = "What size?"
        options = ["S", "M", "L", "XL", "XXL"]

    else:
        # We have enough info — trigger recommendations
        product_desc = f"{current_brand or ''} {current_subcat or current_category}".strip()
        response_text = f"Got it! Let me find the best {product_desc} options for you."
        options = None

    # Remove "_no_preference" sentinel if still present
    if extracted.get("brand") == "_no_preference":
        del extracted["brand"]

    # Handle "no limit" / "no preference" for price
    if "no limit" in user_msg or "no budget" in user_msg:
        extracted["priceRange"] = "0-99999"

    mock_response = {
        "extracted_attributes": extracted,
        "response_text": response_text,
        "options": options,
    }
    return json.dumps(mock_response)


def _create_bedrock_client():
    """Create a boto3 bedrock-runtime client with configured timeout."""
    config = Config(
        read_timeout=settings.BEDROCK_TIMEOUT_SECONDS,
        connect_timeout=settings.BEDROCK_TIMEOUT_SECONDS,
        retries={"max_attempts": 0},  # We handle retries ourselves
    )
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.BEDROCK_REGION,
        config=config,
    )


def invoke_bedrock(
    prompt: str, system_prompt: str | None = None, timeout: int | None = None
) -> str:
    """Invoke Amazon Bedrock (Claude) with the given prompt.

    Args:
        prompt: The user message/prompt to send to Claude.
        system_prompt: Optional system prompt to constrain model behavior.
        timeout: Override timeout in seconds (defaults to settings.BEDROCK_TIMEOUT_SECONDS).

    Returns:
        The model's text response.

    Raises:
        AgentProcessingError: If invocation fails after 1 retry attempt.
    """
    if USE_LOCAL_BEDROCK:
        logger.info("Using local mock Bedrock response (USE_LOCAL_BEDROCK=true)")
        return _get_mock_response(prompt)

    effective_timeout = timeout or settings.BEDROCK_TIMEOUT_SECONDS

    # Build the request body using anthropic.claude messages format
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        body["system"] = system_prompt

    # Retry logic: 1 retry on failure (2 attempts total)
    last_error = None
    for attempt in range(2):
        try:
            client = _create_bedrock_client()

            # Override timeout if specified differently from default
            if effective_timeout != settings.BEDROCK_TIMEOUT_SECONDS:
                config = Config(
                    read_timeout=effective_timeout,
                    connect_timeout=effective_timeout,
                    retries={"max_attempts": 0},
                )
                client = boto3.client(
                    "bedrock-runtime",
                    region_name=settings.BEDROCK_REGION,
                    config=config,
                )

            response = client.invoke_model(
                modelId=settings.BEDROCK_MODEL_ID,
                body=json.dumps(body),
            )

            # Parse response
            response_body = json.loads(response["body"].read())
            output_text = response_body["content"][0]["text"]

            logger.info(
                "Bedrock invocation successful",
                extra={"attempt": attempt + 1, "model_id": settings.BEDROCK_MODEL_ID},
            )
            return output_text

        except (TimeoutError, ClientError) as e:
            last_error = e
            if attempt == 0:
                logger.warning(
                    "Bedrock invocation failed, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "error": str(e),
                        "model_id": settings.BEDROCK_MODEL_ID,
                    },
                )
                continue
            # Second failure — raise user-friendly error
            logger.error(
                "Bedrock invocation failed after retry",
                extra={
                    "attempts": 2,
                    "error": str(e),
                    "model_id": settings.BEDROCK_MODEL_ID,
                },
            )

        except Exception as e:
            last_error = e
            if attempt == 0:
                logger.warning(
                    "Bedrock invocation encountered unexpected error, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "model_id": settings.BEDROCK_MODEL_ID,
                    },
                )
                continue
            logger.error(
                "Bedrock invocation failed after retry with unexpected error",
                extra={
                    "attempts": 2,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "model_id": settings.BEDROCK_MODEL_ID,
                },
            )

    raise AgentProcessingError(
        "I'm having trouble processing your request right now. Please try again in a moment."
    )
