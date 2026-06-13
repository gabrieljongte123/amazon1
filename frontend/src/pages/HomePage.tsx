import { useNavigate } from 'react-router-dom';
import { useEffect, useState, useRef } from 'react';
import CategoryTile from '../components/CategoryTile';
import './HomePage.css';

const categories = [
  { name: 'Grocery', emoji: '🛒', tagline: 'Fresh finds' },
  { name: 'Fashion', emoji: '👗', tagline: 'Style picks' },
  { name: 'Tools', emoji: '🔧', tagline: 'Get it done' },
  { name: 'Electronics', emoji: '📱', tagline: 'Latest tech' },
  { name: 'Essentials', emoji: '🧴', tagline: 'Daily needs' },
  { name: 'Fitness', emoji: '💪', tagline: 'Stay fit' },
  { name: 'Beauty', emoji: '💄', tagline: 'Glow up' },
  { name: 'Pets', emoji: '🐾', tagline: 'Pet care' },
];

const promoSlides = [
  { title: "Min. 40% Off", subtitle: "DIY hand tools & more", badge: "Most Popular This Week", color: "#fef3cd", query: "tools" },
  { title: "Up to 60% Off", subtitle: "Electronics & Gadgets", badge: "🔥 Trending Now", color: "#d4edda", query: "electronics" },
  { title: "Flat ₹200 Off", subtitle: "Beauty & Personal Care", badge: "Limited Time", color: "#f8d7da", query: "beauty products" },
  { title: "Buy 2 Get 1 Free", subtitle: "Grocery Essentials", badge: "⭐ Best Seller", color: "#cce5ff", query: "grocery" },
  { title: "Starting ₹499", subtitle: "Fashion & Footwear", badge: "New Arrivals", color: "#e2d9f3", query: "fashion" },
];

interface PurchasedItem {
  title: string;
  price: number;
  brand: string;
  category: string;
  timestamp: number;
}

function getRecentPurchases(): PurchasedItem[] {
  try {
    const data = sessionStorage.getItem('intentflow-purchases');
    if (data) return JSON.parse(data);
  } catch { /* ignore */ }
  return [];
}

function HomePage() {
  const navigate = useNavigate();
  const [recentPurchases, setRecentPurchases] = useState<PurchasedItem[]>([]);
  const [greeting, setGreeting] = useState('');
  const [currentSlide, setCurrentSlide] = useState(0);
  const slideInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setRecentPurchases(getRecentPurchases());
    const hour = new Date().getHours();
    if (hour < 12) setGreeting('Good morning! ☀️');
    else if (hour < 17) setGreeting('Good afternoon! 🌤️');
    else setGreeting('Good evening! 🌙');
  }, []);

  // Auto-scroll carousel
  useEffect(() => {
    slideInterval.current = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % promoSlides.length);
    }, 3500);
    return () => {
      if (slideInterval.current) clearInterval(slideInterval.current);
    };
  }, []);

  const handleVoiceCTA = () => {
    navigate('/chat');
  };

  const handleBuyAgain = (item: PurchasedItem) => {
    navigate(`/chat?query=Buy ${item.title}`);
  };

  const handleViewCategory = (item: PurchasedItem) => {
    navigate(`/chat?category=${item.category}`);
  };

  return (
    <div className="home-page">
      <section className="home-page__hero">
        <p className="home-page__greeting">{greeting}</p>
        <h1 className="home-page__heading">What are you looking for today?</h1>
        <p className="home-page__subheading">
          Just type or say what you need — I'll find it for you
        </p>
      </section>

      {/* Auto-scrolling deals carousel */}
      <section className="home-page__carousel">
        <div className="carousel" onClick={() => navigate(`/chat?query=${promoSlides[currentSlide].query}`)}>
          {promoSlides.map((slide, idx) => (
            <div
              key={idx}
              className={`carousel__slide ${idx === currentSlide ? 'carousel__slide--active' : ''}`}
              style={{ background: slide.color }}
            >
              <span className="carousel__badge">{slide.badge}</span>
              <h3 className="carousel__title">{slide.title}</h3>
              <p className="carousel__subtitle">{slide.subtitle}</p>
            </div>
          ))}
          <div className="carousel__dots">
            {promoSlides.map((_, idx) => (
              <span
                key={idx}
                className={`carousel__dot ${idx === currentSlide ? 'carousel__dot--active' : ''}`}
                onClick={(e) => { e.stopPropagation(); setCurrentSlide(idx); }}
              />
            ))}
          </div>
        </div>
      </section>

      {/* Quick search bar */}
      <section className="home-page__quick-search">
        <button className="quick-search-btn" onClick={() => navigate('/chat')}>
          <span className="quick-search-btn__icon">🔍</span>
          <span className="quick-search-btn__text">Search for anything...</span>
          <span className="quick-search-btn__mic">🎙️</span>
        </button>
      </section>

      {/* Recent purchases - session cache */}
      {recentPurchases.length > 0 && (
        <section className="home-page__recent">
          <h2 className="home-page__section-title">🕐 Recently Purchased</h2>
          <div className="home-page__recent-grid">
            {recentPurchases.slice(0, 4).map((item, idx) => (
              <div key={idx} className="recent-card">
                <div className="recent-card__info">
                  <span className="recent-card__title">{item.title}</span>
                  {item.price > 0 && (
                    <span className="recent-card__price">₹{item.price.toLocaleString('en-IN')}</span>
                  )}
                  {item.brand && <span className="recent-card__brand">{item.brand}</span>}
                </div>
                <div className="recent-card__actions">
                  <button className="recent-card__buy-again" onClick={() => handleBuyAgain(item)}>
                    🔄 Buy Again
                  </button>
                  <button className="recent-card__view-more" onClick={() => handleViewCategory(item)}>
                    More like this
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Categories */}
      <section className="home-page__categories-section">
        <h2 className="home-page__section-title">🏷️ Browse Categories</h2>
        <div className="home-page__categories" aria-label="Product categories">
          {categories.map((category) => (
            <CategoryTile
              key={category.name}
              name={category.name}
              emoji={category.emoji}
            />
          ))}
        </div>
      </section>

      {/* Deals banner */}
      <section className="home-page__deals">
        <div className="deals-banner" onClick={() => navigate('/chat')}>
          <span className="deals-banner__emoji">⚡</span>
          <div className="deals-banner__text">
            <strong>IntentFlow Deals</strong>
            <span>Ask me for today's best picks in any category</span>
          </div>
          <span className="deals-banner__arrow">→</span>
        </div>
      </section>

      {/* Voice CTA */}
      <section className="home-page__voice-cta">
        <button className="voice-cta-button" onClick={handleVoiceCTA}>
          <span className="voice-cta-button__icon" aria-hidden="true">
            🎙️
          </span>
          <span className="voice-cta-button__text">
            Need something quickly? Talk to Amazon.
          </span>
        </button>
      </section>
    </div>
  );
}

export default HomePage;
