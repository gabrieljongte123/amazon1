import './LoadingIndicator.css';

function LoadingIndicator() {
  return (
    <div className="loading-indicator" aria-label="Agent is typing" role="status">
      <span className="loading-indicator__dot" />
      <span className="loading-indicator__dot" />
      <span className="loading-indicator__dot" />
    </div>
  );
}

export default LoadingIndicator;
