import { useState, useCallback } from 'react';
import { createSession as apiCreateSession } from '../services/api';

interface UseSessionOptions {
  category?: string;
}

interface UseSessionReturn {
  sessionId: string | null;
  isLoading: boolean;
  error: string | null;
  createSession: () => Promise<string | null>;
}

export function useSession(options?: UseSessionOptions): UseSessionReturn {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createSession = useCallback(async (): Promise<string | null> => {
    if (sessionId) return sessionId;

    setIsLoading(true);
    setError(null);

    try {
      const response = await apiCreateSession(options?.category);
      setSessionId(response.sessionId);
      return response.sessionId;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to create session';
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, options?.category]);

  return { sessionId, isLoading, error, createSession };
}
