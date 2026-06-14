import { MessageRole, ResponseType } from '../types';
import type { ChatMessage } from '../hooks/useChat';
import './ChatBubble.css';

interface ChatBubbleProps {
  message: ChatMessage;
  onOptionClick?: (option: string) => void;
}

function ChatBubble({ message, onOptionClick }: ChatBubbleProps) {
  const isUser = message.role === MessageRole.User;
  const isRecommendations = message.responseType === ResponseType.Recommendations;

  return (
    <div className={`chat-bubble ${isUser ? 'chat-bubble--user' : 'chat-bubble--agent'}`}>
      <div className="chat-bubble__content">
        <p className="chat-bubble__text">{message.text}</p>

        {/* Render options as clickable buttons */}
        {!isUser && message.options && message.options.length > 0 && (
          <div className="chat-bubble__options">
            {message.options.map((option) => (
              <button
                key={option}
                className="chat-bubble__option-btn"
                onClick={() => onOptionClick?.(option)}
              >
                {option}
              </button>
            ))}
          </div>
        )}

        {/* Render product recommendations inline */}
        {!isUser && isRecommendations && message.products && message.products.length > 0 && (
          <div className="chat-bubble__products">
            {message.products.map((product) => {
              // Real direct product URL: must contain /dp/ and come from amazon cache
              const hasRealUrl = product.url && 
                product.url.includes('/dp/') && 
                (product.source === 'amazon' || product.source === 'amazon_similar');
              
              // For all products: if real /dp/ URL → use it directly
              // Otherwise → always generate a search URL from THIS product's own title
              const amazonLink = hasRealUrl 
                ? product.url 
                : `https://www.amazon.in/s?k=${encodeURIComponent(product.title)}`;
              
              return (
                <div key={product.productId} className="chat-bubble__product-card">
                  <div className="chat-bubble__product-link-wrapper">
                    {product.imageUrl ? (
                      <img
                        className="chat-bubble__product-img"
                        src={product.imageUrl}
                        alt={product.title}
                        loading="lazy"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    ) : (
                      <div className="chat-bubble__product-img-placeholder">📦</div>
                    )}
                    <div className="chat-bubble__product-info">
                      <span className="chat-bubble__product-title">{product.title}</span>
                      {product.brand && (
                        <span className="chat-bubble__product-brand">{product.brand}</span>
                      )}
                      {product.price > 0 && (
                        <span className="chat-bubble__product-price">₹{product.price.toLocaleString('en-IN')}</span>
                      )}
                      {product.rating > 0 && (
                        <span className="chat-bubble__product-rating">
                          {'★'.repeat(Math.round(product.rating))} {product.rating}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="chat-bubble__product-actions">
                    <button
                      className="chat-bubble__add-cart-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        // Save to session purchase cache
                        try {
                          const purchases = JSON.parse(sessionStorage.getItem('intentflow-purchases') || '[]');
                          purchases.unshift({
                            title: product.title,
                            price: product.price,
                            brand: product.brand || '',
                            category: product.source === 'amazon' ? 'Amazon' : 'IntentFlow',
                            timestamp: Date.now(),
                          });
                          sessionStorage.setItem('intentflow-purchases', JSON.stringify(purchases.slice(0, 10)));
                        } catch { /* ignore */ }
                        // Truncate long titles to prevent ugly chat bubbles
                        const shortTitle = product.title.length > 60 
                          ? product.title.substring(0, 57) + '...' 
                          : product.title;
                        onOptionClick?.(`Add ${shortTitle} to cart`);
                      }}
                    >
                      🛒 Add to Cart
                    </button>
                    <button
                      className="chat-bubble__buy-now-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        // Save to session purchase cache
                        try {
                          const purchases = JSON.parse(sessionStorage.getItem('intentflow-purchases') || '[]');
                          purchases.unshift({
                            title: product.title,
                            price: product.price,
                            brand: product.brand || '',
                            category: product.source === 'amazon' ? 'Amazon' : 'IntentFlow',
                            timestamp: Date.now(),
                          });
                          sessionStorage.setItem('intentflow-purchases', JSON.stringify(purchases.slice(0, 10)));
                        } catch { /* ignore */ }
                        const shortTitle = product.title.length > 60
                          ? product.title.substring(0, 57) + '...'
                          : product.title;
                        onOptionClick?.(`Buy ${shortTitle}`);
                      }}
                    >
                      ⚡ Buy Now
                    </button>
                    {amazonLink && (
                      <a
                        href={amazonLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="chat-bubble__view-amazon-btn"
                        onClick={(e) => e.stopPropagation()}
                        title={hasRealUrl ? 'View on Amazon' : `Search "${product.title}" on Amazon`}
                      >
                        {hasRealUrl ? '🔗 Amazon' : '🔍 Search'}
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatBubble;
