import { useState, useCallback, useRef } from 'react';
import { sendMessage as apiSendMessage } from '../services/api';
import type { AgentResponsePayload } from '../types';
import { MessageRole, ResponseType } from '../types';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  timestamp: string;
  options?: string[];
  products?: AgentResponsePayload['products'];
  responseType?: ResponseType;
}

interface UseChatReturn {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  addAgentMessage: (text: string) => void;
}

let messageIdCounter = 0;

function generateMessageId(): string {
  messageIdCounter += 1;
  return `msg-${Date.now()}-${messageIdCounter}`;
}

export function useChat(sessionId: string | null): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const addAgentMessage = useCallback((text: string) => {
    const agentMessage: ChatMessage = {
      id: generateMessageId(),
      role: MessageRole.Agent,
      text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, agentMessage]);
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!sessionId) {
        setError('No active session. Please try refreshing.');
        return;
      }

      const trimmedText = text.trim();
      if (!trimmedText) return;

      // Add user message to the array
      const userMessage: ChatMessage = {
        id: generateMessageId(),
        role: MessageRole.User,
        text: trimmedText,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setError(null);

      // Set up 30-second timeout
      abortControllerRef.current = new AbortController();
      const timeoutId = setTimeout(() => {
        abortControllerRef.current?.abort();
      }, 30000);

      try {
        const response = await apiSendMessage(sessionId, trimmedText);

        const agentMessage: ChatMessage = {
          id: generateMessageId(),
          role: MessageRole.Agent,
          text: response.response.text,
          timestamp: new Date().toISOString(),
          options: response.response.options,
          products: response.response.products,
          responseType: response.response.type,
        };

        setMessages((prev) => [...prev, agentMessage]);
        setError(null);
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setError('Request timed out. Please try again.');
        } else {
          const message =
            err instanceof Error
              ? err.message
              : 'Something went wrong. Please try again.';
          setError(message);
        }
      } finally {
        clearTimeout(timeoutId);
        abortControllerRef.current = null;
        setIsLoading(false);
      }
    },
    [sessionId],
  );

  return { messages, isLoading, error, sendMessage, addAgentMessage };
}
