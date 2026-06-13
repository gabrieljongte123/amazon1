import { useState, useEffect } from 'react';
import './ConnectionStatus.css';

function ConnectionStatus() {
  const [isOffline, setIsOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const handleOffline = () => setIsOffline(true);
    const handleOnline = () => setIsOffline(false);

    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);

    return () => {
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
    };
  }, []);

  return (
    <div
      className={`connection-status ${isOffline ? 'connection-status--visible' : ''}`}
      role="alert"
      aria-live="assertive"
    >
      <span className="connection-status__icon" aria-hidden="true" />
      <span>Connection lost. Waiting for network…</span>
    </div>
  );
}

export default ConnectionStatus;
