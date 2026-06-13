import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import ChatPage from './pages/ChatPage';
import CartConfirmation from './pages/CartConfirmation';
import ConnectionStatus from './components/ConnectionStatus';
import './App.css';

function AppHeader() {
  const navigate = useNavigate();
  return (
    <header className="app-header">
      <div className="app-header__left" onClick={() => navigate('/')} style={{cursor: 'pointer'}}>
        <img src="/amazon.jpg" alt="Amazon" className="app-header__logo-img" />
        <span className="app-header__title">IntentFlow</span>
      </div>
      <div className="app-header__right">
        <span className="app-header__tagline">Intent-First Shopping</span>
      </div>
    </header>
  );
}

function App() {
  return (
    <BrowserRouter>
      <ConnectionStatus />
      <div className="app">
        <AppHeader />
        <main className="app-main">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/cart-confirmation" element={<CartConfirmation />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
