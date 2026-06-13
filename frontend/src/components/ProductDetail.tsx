import type { Product } from '../types';
import './ProductDetail.css';

interface ProductDetailProps {
  product: Product;
  onBack: () => void;
  onAddToCart: (productId: string) => void;
  isAddingToCart?: boolean;
}

function renderStars(rating: number): string {
  const full = Math.floor(rating);
  const half = rating - full >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty);
}

function formatPrice(price: number): string {
  return `₹${price.toLocaleString('en-IN')}`;
}

function ProductDetail({ product, onBack, onAddToCart, isAddingToCart }: ProductDetailProps) {
  return (
    <div className="product-detail">
      <button
        className="product-detail__back-button"
        onClick={onBack}
        type="button"
        aria-label="Back to recommendations"
      >
        ← Back to recommendations
      </button>

      <div className="product-detail__image-container">
        {product.imageUrl ? (
          <img
            className="product-detail__image"
            src={product.imageUrl}
            alt={product.title}
          />
        ) : (
          <span className="product-detail__image-placeholder" aria-hidden="true">
            📦
          </span>
        )}
      </div>

      <div className="product-detail__info">
        <h2 className="product-detail__title">{product.title}</h2>

        {product.brand && (
          <span className="product-detail__brand">by {product.brand}</span>
        )}

        <span className="product-detail__price">{formatPrice(product.price)}</span>

        <div className="product-detail__rating">
          <span className="product-detail__stars" aria-hidden="true">
            {renderStars(product.rating)}
          </span>
          <span className="product-detail__rating-value">
            {product.rating.toFixed(1)} out of 5
          </span>
        </div>

        <div className="product-detail__attributes">
          {product.size && (
            <span className="product-detail__attribute">
              <span className="product-detail__attribute-label">Size:</span> {product.size}
            </span>
          )}
          {product.color && (
            <span className="product-detail__attribute">
              <span className="product-detail__attribute-label">Color:</span> {product.color}
            </span>
          )}
        </div>
      </div>

      <button
        className="product-detail__add-to-cart"
        onClick={() => onAddToCart(product.productId)}
        disabled={isAddingToCart}
        type="button"
      >
        {isAddingToCart ? 'Adding...' : 'Add to Cart'}
      </button>
    </div>
  );
}

export default ProductDetail;
