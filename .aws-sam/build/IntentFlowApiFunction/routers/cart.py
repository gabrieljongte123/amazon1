"""Cart operations router for IntentFlow.

Handles add-to-cart validation and response (prototype — no persistent cart).
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from models.cart import CartRequest
from services.product_catalog import get_product_by_id

router = APIRouter(prefix="/cart", tags=["cart"])


@router.post("/items")
async def add_to_cart(
    body: CartRequest,
    request: Request,
):
    """Add a product to cart.

    For the prototype, validates the product exists and returns
    a confirmation response without persisting cart state.
    """
    correlation_id: str = getattr(request.state, "correlation_id", "unknown")

    # Verify product exists
    product = get_product_by_id(body.product_id)
    if product is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "The requested product is unavailable.",
                    "correlationId": correlation_id,
                }
            },
        )

    # Prototype: return confirmation without persisting cart state
    return JSONResponse(
        status_code=200,
        content={
            "productId": product.product_id,
            "title": product.title,
            "quantity": body.quantity,
            "price": product.price,
            "cartItemCount": 1,
        },
    )
