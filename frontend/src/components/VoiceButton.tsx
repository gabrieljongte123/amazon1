import './VoiceButton.css';

interface VoiceButtonProps {
  isRecording: boolean;
  onClick: () => void;
  disabled?: boolean;
}

/**
 * Microphone button with pulsing animation during active listening.
 * Toggles start/stop on click.
 */
function VoiceButton({ isRecording, onClick, disabled = false }: VoiceButtonProps) {
  const label = isRecording ? 'Stop recording' : 'Start voice input';

  return (
    <button
      type="button"
      className={`voice-button${isRecording ? ' voice-button--recording' : ''}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
    >
      {isRecording && <span className="voice-button__pulse" aria-hidden="true" />}
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {/* Microphone icon */}
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="23" />
        <line x1="8" y1="23" x2="16" y2="23" />
      </svg>
    </button>
  );
}

export default VoiceButton;
