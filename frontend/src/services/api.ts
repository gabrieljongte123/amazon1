import axios from 'axios';
import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import type {
  ApiError,
  CreateSessionRequest,
  CreateSessionResponse,
  MessageResponse,
  RecommendationsResponse,
  CartRequest,
  CartResponse,
} from '../types';

// ─── Configuration ────────────────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const MAX_RETRIES = 3;
const BACKOFF_MS = [1000, 2000, 4000];
const USER_ID_KEY = 'intentflow-user-id';

// ─── Axios Instance ───────────────────────────────────────────────────────────

const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach X-User-Id header from localStorage on each request
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const userId = localStorage.getItem(USER_ID_KEY);
  if (userId) {
    config.headers['X-User-Id'] = userId;
  }
  return config;
});

// Store user ID from responses
apiClient.interceptors.response.use((response) => {
  if (response.data?.userId) {
    localStorage.setItem(USER_ID_KEY, response.data.userId);
  }
  return response;
});

// ─── User-Friendly Error Messages ────────────────────────────────────────────

const USER_FRIENDLY_MESSAGES: Record<number, string> = {
  400: 'Please check your input and try again.',
  404: "Your session has expired. Let's start fresh!",
  429: "You're going too fast. Please wait a moment.",
  502: 'Something went wrong. Please try again.',
  503: "We're experiencing high demand. Try again shortly.",
  504: 'This is taking too long. Please try again.',
};

const DEFAULT_ERROR_MESSAGE = 'Something went wrong. Please try again.';

/**
 * Returns a non-technical, user-facing error message for an API error.
 */
export function getUserFriendlyMessage(error: unknown): string {
  if (axios.isAxiosError(error) && error.response) {
    const status = error.response.status;
    return USER_FRIENDLY_MESSAGES[status] || DEFAULT_ERROR_MESSAGE;
  }
  if (!navigator.onLine) {
    return 'Connection lost. Waiting for network…';
  }
  return DEFAULT_ERROR_MESSAGE;
}

// ─── Error Extraction ─────────────────────────────────────────────────────────

export function extractApiError(error: unknown): ApiError | null {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiError>;
    if (axiosError.response?.data?.error) {
      return axiosError.response.data;
    }
  }
  return null;
}

// ─── Retry Logic ──────────────────────────────────────────────────────────────

async function withRetry<T>(fn: () => Promise<T>): Promise<T> {
  let lastError: unknown;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      // Don't retry on client errors (4xx) except 429
      if (axios.isAxiosError(error) && error.response) {
        const status = error.response.status;
        if (status >= 400 && status < 500 && status !== 429) {
          throw error;
        }
      }

      // Don't retry if we've exhausted attempts
      if (attempt >= MAX_RETRIES) {
        break;
      }

      // Wait with exponential backoff
      await new Promise((resolve) => setTimeout(resolve, BACKOFF_MS[attempt]));
    }
  }

  throw lastError;
}

// ─── API Functions ────────────────────────────────────────────────────────────

export async function createSession(
  category?: string,
): Promise<CreateSessionResponse> {
  const body: CreateSessionRequest = category ? { category } : {};
  const response = await withRetry(() => apiClient.post('/sessions', body));
  return response.data;
}

export async function sendMessage(
  sessionId: string,
  text: string,
): Promise<MessageResponse> {
  const response = await withRetry(() =>
    apiClient.post(`/sessions/${sessionId}/messages`, { text }),
  );
  return response.data;
}

export async function getRecommendations(
  sessionId: string,
): Promise<RecommendationsResponse> {
  const response = await withRetry(() =>
    apiClient.get(`/sessions/${sessionId}/recommendations`),
  );
  return response.data;
}

export async function addToCart(
  productId: string,
  quantity: number,
): Promise<CartResponse> {
  const body: CartRequest = { productId, quantity };
  const response = await withRetry(() => apiClient.post('/cart/items', body));
  return response.data;
}

export default apiClient;
