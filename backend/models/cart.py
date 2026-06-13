"""Cart data models for IntentFlow."""

from pydantic import BaseModel, Field


class CartRequest(BaseModel):
    """Request body for POST /cart/items."""

    product_id: str = Field(
        ...,
        alias="productId",
        min_length=1,
        description="Product identifier to add to cart",
    )
    quantity: int = Field(
        ...,
        ge=1,
        le=10,
        description="Quantity to add (1-10)",
    )

    model_config = {"populate_by_name": True}


class CartResponse(BaseModel):
    """Response body for POST /cart/items."""

    product_id: str = Field(..., alias="productId", description="Product identifier")
    title: str = Field(..., description="Product title")
    quantity: int = Field(..., ge=1, le=10, description="Quantity added")
    price: int = Field(..., gt=0, description="Product price")
    cart_item_count: int = Field(
        ...,
        alias="cartItemCount",
        ge=1,
        description="Total items in cart after addition",
    )

    model_config = {"populate_by_name": True}
