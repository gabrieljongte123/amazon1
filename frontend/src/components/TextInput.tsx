import { useState, useRef, type KeyboardEvent, type FormEvent } from 'react';
import './TextInput.css';

interface TextInputProps {
  onSend: (text: string) => void;
  isLoading: boolean;
  error: string | null;
}

const MAX_LENGTH = 500;

function TextInput({ onSend, isLoading, error }: TextInputProps) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e?: FormEvent) => {
    e?.preventDefault();

    const trimmed = text.trim();
    if (!trimmed || isLoading) {
      // Keep input focused on empty/whitespace rejection
      inputRef.current?.focus();
      return;
    }

    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="text-input-wrapper">
      {error && (
        <div className="text-input__error" role="alert">
          {error}
        </div>
      )}
      <form className="text-input" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          className="text-input__field"
          placeholder={isLoading ? 'Waiting for response...' : 'Type your message...'}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          maxLength={MAX_LENGTH}
          disabled={isLoading}
          aria-label="Message input"
          autoComplete="off"
        />
        <button
          type="submit"
          className="text-input__send-btn"
          disabled={isLoading || !text.trim()}
          aria-label="Send message"
        >
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
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </form>
      {text.length > MAX_LENGTH - 50 && (
        <span className="text-input__counter">
          {text.length}/{MAX_LENGTH}
        </span>
      )}
    </div>
  );
}

export default TextInput;
