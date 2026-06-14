"""Product data models for IntentFlow."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class Product(BaseModel):
    """Full product model matching the product catalog schema."""

    product_id: str = Field(..., alias="productId", description="Unique product identifier")
    title: str = Field(..., min_length=1, description="Product title")
    category: str = Field(..., min_length=1, description="Product category")
    brand: str = Field(..., min_length=1, description="Product brand")
    price: int = Field(..., gt=0, description="Product price in minor currency units")
    size: str | None = Field(default=None, description="Product size (where applicable)")
    color: str | None = Field(default=None, description="Product color (where applicable)")
    rating: float = Field(
        ...,
        ge=1.0,
        le=5.0,
        description="Customer rating (1.0-5.0)",
    )
    image_url: str = Field(..., alias="imageUrl", description="Product image URL")
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional searchable attributes (key-value pairs)",
    )

    model_config = {"populate_by_name": True}

    @field_validator("rating")
    @classmethod
    def validate_rating_precision(cls, v: float) -> float:
        """Ensure rating is in 0.1 increments."""
        if round(v * 10) != v * 10:
            raise ValueError("rating must be in 0.1 increments")
        return v


class ProductSummary(BaseModel):
    """Abbreviated product info for recommendation cards."""

    product_id: str = Field(..., alias="productId", description="Unique product identifier")
    title: str = Field(..., description="Product title")
    price: int = Field(..., gt=0, description="Product price")
    rating: float = Field(..., ge=1.0, le=5.0, description="Customer rating")
    image_url: str = Field(..., alias="imageUrl", description="Product image URL")

    model_config = {"populate_by_name": True}
