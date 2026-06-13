import type { Product } from '../types';
import './RecommendationCard.css';

interface RecommendationCardProps {
  product: Product;
  onSelect: (product: Product) => void;
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

function RecommendationCard({ product, onSelect }: RecommendationCardProps) {
  return (
    <button
      className="recommendation-card"
      onClick={() => onSelect(product)}
      aria-label={`View details for ${product.title}`}
      type="button"
    >
      <div className="recommendation-card__image-container">
        {product.imageUrl ? (
          <img
            className="recommendation-card__image"
            src={product.imageUrl}
            alt={product.title}
            loading="lazy"
          />
        ) : (
          <span className="recommendation-card__image-placeholder" aria-hidden="true">
            📦
          </span>
        )}
      </div>
      <div className="recommendation-card__content">
        <span className="recommendation-card__title">{product.title}</span>
        <span className="recommendation-card__price">{formatPrice(product.price)}</span>
        <span className="recommendation-card__rating">
          <span className="recommendation-card__stars" aria-hidden="true">
            {renderStars(product.rating)}
          </span>
          <span>{product.rating.toFixed(1)}</span>
        </span>
      </div>
    </button>
  );
}

export default RecommendationCard;
