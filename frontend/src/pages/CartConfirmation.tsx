import { useNavigate, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { useCart } from '../hooks/useCart';
import './CartConfirmation.css';

interface CartConfirmationState {
  productId: string;
  title: string;
  price: number;
  quantity?: number;
}

function formatPrice(price: number): string {
  return `₹${price.toLocaleString('en-IN')}`;
}

function CartConfirmation() {
  const navigate = useNavigate();
  const location = useLocation();
  const { addToCart, isLoading, error, cartItem } = useCart();

  const state = location.state as CartConfirmationState | null;

  useEffect(() => {
    if (state?.productId) {
      addToCart(state.productId, state.quantity || 1);
    }
  }, [state?.productId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleRetry = () => {
    if (state?.productId) {
      addToCart(state.productId, state.quantity || 1);
    }
  };

  const handleContinueShopping = () => {
    navigate('/');
  };

  const handleReturnToRecommendations = () => {
    navigate(-1);
  };

  // No product state passed — redirect home
  if (!state) {
    return (
      <div className="cart-confirmation">
        <div className="cart-confirmation__error">
          <div className="cart-confirmation__error-icon" aria-hidden="true">!</div>
          <p className="cart-confirmation__error-message">
            No product selected. Please choose a product first.
          </p>
          <button
            className="cart-confirmation__continue-button"
            onClick={handleContinueShopping}
            type="button"
          >
            Continue Shopping
          </button>
        </div>
      </div>
    );
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="cart-confirmation">
        <div className="cart-confirmation__loading">
          <div className="cart-confirmation__spinner" aria-label="Adding to cart" />
          <p>Adding to cart...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    const isUnavailable = error.toLowerCase().includes('unavailable') ||
      error.toLowerCase().includes('not found');

    return (
      <div className="cart-confirmation">
        <div className="cart-confirmation__error">
          <div className="cart-confirmation__error-icon" aria-hidden="true">!</div>
          <p className="cart-confirmation__error-message">{error}</p>

          {isUnavailable ? (
            <button
              className="cart-confirmation__unavailable-link"
              onClick={handleReturnToRecommendations}
              type="button"
            >
              Return to recommendations
            </button>
          ) : (
            <button
              className="cart-confirmation__retry-button"
              onClick={handleRetry}
              type="button"
            >
              Try Again
            </button>
          )}

          <button
            className="cart-confirmation__continue-button"
            onClick={handleContinueShopping}
            type="button"
          >
            Continue Shopping
          </button>
        </div>
      </div>
    );
  }

  // Success state
  if (cartItem) {
    return (
      <div className="cart-confirmation">
        <div className="cart-confirmation__success-icon" aria-hidden="true">✓</div>
        <h1 className="cart-confirmation__heading">Added to Cart</h1>

        <div className="cart-confirmation__product">
          <span className="cart-confirmation__product-title">{cartItem.title}</span>
          <div className="cart-confirmation__product-details">
            <span>Qty: {cartItem.quantity}</span>
            <span className="cart-confirmation__product-price">
              {formatPrice(cartItem.price)}
            </span>
          </div>
        </div>

        <div className="cart-confirmation__actions">
          <button
            className="cart-confirmation__checkout-button"
            type="button"
            onClick={() => {/* No actual checkout */}}
          >
            Proceed to Checkout
          </button>
          <button
            className="cart-confirmation__continue-button"
            onClick={handleContinueShopping}
            type="button"
          >
            Continue Shopping
          </button>
        </div>
      </div>
    );
  }

  return null;
}

export default CartConfirmation;
