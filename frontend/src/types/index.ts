// IntentFlow TypeScript type definitions

// ─── Enums ────────────────────────────────────────────────────────────────────

export enum MessageRole {
  User = 'user',
  Agent = 'agent',
}

export enum ResponseType {
  Question = 'question',
  Recommendations = 'recommendations',
}

// ─── Core Domain Models ───────────────────────────────────────────────────────

export interface Session {
  sessionId: string;
  userId: string;
  message?: string;
}

export interface Message {
  role: MessageRole;
  text: string;
  timestamp: string;
}

export interface Product {
  productId: string;
  title: string;
  category: string;
  brand: string;
  price: number;
  size?: string;
  color?: string;
  rating: number;
  imageUrl: string;
  url?: string;
  source?: string;
  attributes?: Record<string, string>;
}

export interface CartItem {
  productId: string;
  title: string;
  quantity: number;
  price: number;
  cartItemCount: number;
}

// ─── Metadata ─────────────────────────────────────────────────────────────────

export interface Metadata {
  confidenceScore: number;
  extractedAttributes: Record<string, string>;
  questionCount: number;
}

// ─── Agent Response ───────────────────────────────────────────────────────────

export interface AgentResponsePayload {
  type: ResponseType;
  text: string;
  options?: string[];
  products?: Product[];
}

export interface AgentResponse {
  sessionId: string;
  response: AgentResponsePayload;
  metadata: Metadata;
}

// ─── API Request/Response Types ───────────────────────────────────────────────

/** POST /sessions - Request */
export interface CreateSessionRequest {
  category?: string;
}

/** POST /sessions - Response (201 Created) */
export interface CreateSessionResponse {
  sessionId: string;
  message: string;
  userId: string;
}

/** POST /sessions/{sessionId}/messages - Request */
export interface MessageRequest {
  text: string;
}

/** POST /sessions/{sessionId}/messages - Response (200 OK) */
export interface MessageResponse {
  sessionId: string;
  response: AgentResponsePayload;
  metadata: Metadata;
}

/** GET /sessions/{sessionId}/recommendations - Response (200 OK) */
export interface RecommendationsResponse {
  products: Product[];
  explanation: string;
}

/** POST /cart/items - Request */
export interface CartRequest {
  productId: string;
  quantity: number;
}

/** POST /cart/items - Response (200 OK) */
export interface CartResponse {
  productId: string;
  title: string;
  quantity: number;
  price: number;
  cartItemCount: number;
}

// ─── Error Handling ───────────────────────────────────────────────────────────

export interface ApiError {
  error: {
    code: string;
    message: string;
    correlationId: string;
  };
}

// ─── Generic API Response Wrapper ─────────────────────────────────────────────

export type ApiResponse<T> = T | ApiError;
