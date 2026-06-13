import { useRef, useEffect, useState, useCallback } from 'react';
import ChatBubble from './ChatBubble';
import LoadingIndicator from './LoadingIndicator';
import type { ChatMessage } from '../hooks/useChat';
import './ChatThread.css';

interface ChatThreadProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onOptionClick?: (option: string) => void;
}

function ChatThread({ messages, isLoading, onOptionClick }: ChatThreadProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const prevMessageCountRef = useRef(messages.length);

  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
      setHasNewMessages(false);
      setIsUserScrolledUp(false);
    }
  }, []);

  // Detect user scroll
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    // Consider "scrolled up" if more than 100px from the bottom
    setIsUserScrolledUp(distanceFromBottom > 100);
  };

  // Auto-scroll on new messages unless user scrolled up
  useEffect(() => {
    if (messages.length > prevMessageCountRef.current) {
      if (isUserScrolledUp) {
        setHasNewMessages(true);
      } else {
        scrollToBottom();
      }
    }
    prevMessageCountRef.current = messages.length;
  }, [messages.length, isUserScrolledUp, scrollToBottom]);

  // Auto-scroll when loading starts (typing indicator appears)
  useEffect(() => {
    if (isLoading && !isUserScrolledUp) {
      scrollToBottom();
    }
  }, [isLoading, isUserScrolledUp, scrollToBottom]);

  return (
    <div className="chat-thread" ref={containerRef} onScroll={handleScroll}>
      <div className="chat-thread__messages">
        {messages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} onOptionClick={onOptionClick} />
        ))}
        {isLoading && (
          <div className="chat-bubble chat-bubble--agent">
            <div className="chat-bubble__content">
              <LoadingIndicator />
            </div>
          </div>
        )}
      </div>

      {hasNewMessages && isUserScrolledUp && (
        <button
          className="chat-thread__new-messages"
          onClick={scrollToBottom}
          aria-label="Scroll to new messages"
        >
          ↓ New messages
        </button>
      )}
    </div>
  );
}

export default ChatThread;
