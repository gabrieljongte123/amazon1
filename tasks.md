# Implementation Plan: IntentFlow

## Overview

Build an AI-driven conversational commerce prototype using React (Vite + TypeScript) frontend, FastAPI (Python) backend on AWS Lambda, Amazon Bedrock (Claude) for NLU, Amazon Transcribe for voice, and DynamoDB for session persistence. Tasks are ordered for fastest time-to-working-demo: scaffold → data → core engine → API → frontend → integrations → polish.

## Tasks

- [x] 1. Project scaffolding and core interfaces
  - [x] 1.1 Set up React frontend with Vite and TypeScript
    - Initialize Vite project with React + TypeScript template in `frontend/`
    - Install dependencies: react-router-dom, axios
    - Configure path aliases, ESLint, Prettier
    - Create directory structure: `src/pages/`, `src/components/`, `src/hooks/`, `src/services/`, `src/types/`
    - _Requirements: 1.1, 1.5_

  - [x] 1.2 Set up FastAPI backend with project structure
    - Initialize Python project in `backend/` with `pyproject.toml` or `requirements.txt`
    - Install dependencies: fastapi, mangum, boto3, pydantic, uvicorn
    - Create directory structure: `routers/`, `services/`, `models/`, `middleware/`
    - Create `main.py` with FastAPI app instance and Mangum handler
    - Create `config.py` with environment configuration (DynamoDB table name, Bedrock model ID, confidence threshold, rate limit)
    - _Requirements: 12.2_

  - [x] 1.3 Define TypeScript interfaces and types
    - Create `src/types/index.ts` with interfaces: Session, Message, Product, CartItem, ApiResponse, AgentResponse (question vs recommendations), Metadata
    - Define enums for message role (user/agent), response type (question/recommendations)
    - _Requirements: 4.1, 8.1, 11.2_

  - [x] 1.4 Define Python data models with Pydantic
    - Create `models/session.py`: Session model with sessionId, userId, conversationHistory, extractedAttributes, confidenceScore, questionCount, timestamps, ttl
    - Create `models/message.py`: MessageRequest (text field, max 500 chars), MessageResponse (type, text, options, products, metadata)
    - Create `models/product.py`: Product model with all catalog fields
    - Create `models/cart.py`: CartRequest (productId, quantity 1-10), CartResponse
    - _Requirements: 3.1, 11.5, 14.3_

- [x] 2. Product catalog and data layer
  - [x] 2.1 Create mock product catalog JSON
    - Create `backend/data/products.json` with 50+ products (10+ per category) across Grocery, Fashion, Tools, Electronics, Essentials
    - Each product: productId, title, category, brand, price, size, color, rating (1.0-5.0), imageUrl, attributes map
    - Include `categories` schema defining requiredAttributes, optionalAttributes, and discriminativeOrder per category
    - _Requirements: 15.1, 15.2, 15.3_

  - [x] 2.2 Implement product catalog service
    - Create `backend/services/product_catalog.py`
    - Load products from JSON on cold start (module-level caching)
    - Implement `query_products(attributes: dict) -> list[Product]` with exact match for categorical attributes and range containment for price
    - Implement `count_matching_products(attributes: dict) -> int`
    - Implement `get_product_by_id(product_id: str) -> Product | None`
    - Return empty list when no products match
    - _Requirements: 15.4, 15.5_

  - [ ]* 2.3 Write property test for catalog query correctness
    - **Property 10: Catalog query correctness**
    - Generate random filter attribute combinations and verify every returned product matches ALL specified filters
    - **Validates: Requirements 15.4, 15.5**

  - [ ]* 2.4 Write property test for recommendation sorting and limit
    - **Property 9: Recommendation sorting and limit**
    - Generate random product lists, verify sorting is descending by rating and max 5 returned
    - **Validates: Requirements 8.1**

- [x] 3. DynamoDB session store
  - [x] 3.1 Implement session store service
    - Create `backend/services/session_store.py`
    - Implement `create_session(session_id: str, user_id: str, category: str | None) -> Session`
    - Implement `get_session(session_id: str) -> Session | None`
    - Implement `update_session(session: Session) -> None` (sets updatedAt and TTL = updatedAt + 1800s)
    - Handle DynamoDB errors: propagate without modifying state, 5-second timeout
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

  - [ ]* 3.2 Write property test for session round-trip preservation
    - **Property 3: Session state round-trip preservation**
    - Generate random valid session states and verify write-then-read produces identical state
    - **Validates: Requirements 4.2, 14.5**

  - [ ]* 3.3 Write property test for session persistence invariants
    - **Property 12: Session persistence invariants**
    - Verify updatedAt is current, all required fields present, TTL = updatedAt + 1800
    - **Validates: Requirements 14.2, 14.3, 14.4**

- [x] 4. Intent Compression Engine
  - [x] 4.1 Implement confidence score calculation
    - Create `backend/services/compression_engine.py`
    - Implement `calculate_confidence(session: Session) -> float` using weighted formula: `(|known ∩ required| × 2 + |known ∩ optional|) / (|required| × 2 + |optional|)`, clamped to [0.0, 1.0]
    - Without category: return `len(known_attributes) / 10.0`
    - _Requirements: 6.2, 6.3_

  - [x] 4.2 Implement should_recommend decision logic
    - Implement `should_recommend(session: Session, confidence: float) -> bool`
    - Return True if: question_count >= 5, OR confidence >= threshold (0.8), OR matching products > 0 and < 4
    - Return False otherwise
    - _Requirements: 6.6, 7.1, 7.2, 7.3_

  - [x] 4.3 Implement information gain calculation and next question selection
    - Implement `calculate_information_gain(candidates: list, attribute: str) -> float` using entropy
    - Implement `select_next_question(session: Session) -> str` prioritizing category first, then highest information gain attribute
    - Use discriminativeOrder from category schema as tiebreaker
    - _Requirements: 6.1, 6.4_

  - [x] 4.4 Implement process_message orchestration
    - Implement `process_message(session: Session, new_attributes: dict) -> AgentAction`
    - Merge new attributes, calculate confidence, decide recommend vs question
    - Return AgentAction with type "recommendations" or "question"
    - _Requirements: 7.1, 7.4_

  - [ ]* 4.5 Write property test for confidence score correctness
    - **Property 6: Confidence score correctness**
    - Generate random category schemas and known attribute subsets, verify formula output
    - **Validates: Requirements 6.2**

  - [ ]* 4.6 Write property test for confidence monotonicity
    - **Property 7: Confidence monotonicity**
    - Generate sessions, add attributes, verify confidence never decreases
    - **Validates: Requirements 6.3**

  - [ ]* 4.7 Write property test for recommendation trigger invariants
    - **Property 8: Recommendation trigger invariants**
    - Generate random session states, verify should_recommend matches spec conditions
    - **Validates: Requirements 6.6, 7.1, 7.3**

  - [ ]* 4.8 Write property test for information gain maximization
    - **Property 5: Information gain maximization**
    - Generate candidate product lists and unknown attributes, verify selected attribute has highest entropy
    - **Validates: Requirements 6.1, 6.4**

- [x] 5. Attribute merge and intent extraction
  - [x] 5.1 Implement attribute merge logic
    - Create utility in `backend/services/intent_agent.py` or `compression_engine.py`
    - Implement `merge_attributes(existing: dict, new: dict) -> dict`: new keys override, existing keys not in new are preserved
    - _Requirements: 5.2, 5.3_

  - [ ]* 5.2 Write property test for attribute merge semantics
    - **Property 4: Attribute merge semantics**
    - Generate random existing and new attribute maps, verify override and preservation rules
    - **Validates: Requirements 5.2, 5.3**

- [x] 6. Checkpoint - Core engine tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Amazon Bedrock integration
  - [x] 7.1 Implement Bedrock client
    - Create `backend/services/bedrock_client.py`
    - Implement `invoke_bedrock(prompt: str, timeout: int = 15) -> str` with 1 retry on failure
    - Handle TimeoutError and service errors; raise AgentProcessingError with user-friendly message on double failure
    - _Requirements: 13.1, 13.3_

  - [x] 7.2 Implement prompt construction
    - Build system prompt constraining responses to shopping domain
    - Include last 20 messages from conversation history and all extracted attributes in prompt
    - Include instructions for attribute extraction (return JSON with extracted attributes)
    - Include response formatting constraints (max 2 sentences for questions, 5 options max)
    - _Requirements: 13.2, 13.4, 13.5, 19.1, 19.2, 19.3_

  - [ ]* 7.3 Write property test for prompt construction context window
    - **Property 11: Prompt construction includes context window**
    - Generate histories of various lengths, verify exactly min(N, 20) messages included plus all attributes
    - **Validates: Requirements 13.2**

- [x] 8. IntentFlow Agent orchestration
  - [x] 8.1 Implement IntentFlow Agent service
    - Create `backend/services/intent_agent.py`
    - Implement `process_user_message(session: Session, text: str) -> AgentResponse`
    - Flow: invoke Bedrock → extract attributes from response → merge into session → pass to compression engine → return question or recommendations
    - Handle case where no attributes extracted: ask clarifying question (track consecutive no-extract count, show categories after 3)
    - _Requirements: 5.1, 5.4, 5.5, 7.4, 7.5_

  - [x] 8.2 Implement recommendation retrieval and formatting
    - Query product catalog with known attributes, return up to 5 sorted by rating descending
    - Generate explanation (max 2 sentences) referencing known attributes
    - Handle zero results: suggest broadening preferences
    - _Requirements: 8.1, 8.4, 8.5_

  - [ ]* 8.3 Write property test for response formatting constraints
    - **Property 14: Response formatting constraints**
    - Generate random agent responses, verify: options ≤ 5 items each ≤ 10 words, questions ≤ 2 sentences, non-questions ≤ 3 sentences
    - **Validates: Requirements 19.2, 19.3**

- [x] 9. Backend API endpoints
  - [x] 9.1 Implement middleware stack
    - Create `backend/middleware/auth.py`: extract X-User-Id header, validate (1-64 chars, non-empty), generate UUID v4 if missing, return 400 if invalid
    - Create `backend/middleware/correlation.py`: generate unique correlation ID per request, attach to logs and responses
    - Create `backend/middleware/logging.py`: structured JSON logging with session_id, request_type, response_latency_ms, correlation_id
    - _Requirements: 17.1, 17.2, 17.3, 18.1, 18.2, 18.4_

  - [ ]* 9.2 Write property test for user ID validation
    - **Property 13: User ID validation**
    - Generate strings of various lengths, verify acceptance/rejection/generation behavior
    - **Validates: Requirements 18.1, 18.2, 18.4**

  - [x] 9.3 Implement POST /sessions endpoint
    - Create `backend/routers/sessions.py`
    - Accept optional category in body, create session in DynamoDB, return session ID + welcome message + user ID
    - _Requirements: 4.1, 11.1_

  - [x] 9.4 Implement POST /sessions/{sessionId}/messages endpoint
    - Create `backend/routers/messages.py`
    - Validate session exists (404 if not), validate text field (non-empty, max 500 chars)
    - Load session, invoke IntentFlow Agent, update session state, return response
    - Show loading timeout of 29s (Lambda limit)
    - _Requirements: 4.3, 4.4, 4.5, 11.2, 12.3_

  - [x] 9.5 Implement GET /sessions/{sessionId}/recommendations endpoint
    - Create `backend/routers/recommendations.py`
    - Validate session exists, query catalog with current attributes, return products + explanation
    - _Requirements: 11.3_

  - [x] 9.6 Implement POST /cart/items endpoint
    - Create `backend/routers/cart.py`
    - Validate productId exists and quantity (1-10), verify product available in catalog
    - Return product details + cart item count, or 404 if product unavailable
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 11.4_

  - [x] 9.7 Implement rate limiting middleware
    - Implement per-user rate limiting: 100 requests per minute
    - Return HTTP 429 with appropriate error message when exceeded
    - Use in-memory counter (acceptable for prototype; production would use Redis/DynamoDB)
    - _Requirements: 20.4, 20.5_

  - [ ]* 9.8 Write unit tests for API endpoints
    - Test all 4 endpoints with valid and invalid inputs
    - Test 400 validation errors, 404 session not found, 429 rate limit
    - Test error response format includes correlationId
    - _Requirements: 11.5, 11.6_

- [x] 10. Checkpoint - Backend API working
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Frontend homepage and routing
  - [x] 11.1 Set up React Router and app layout
    - Configure routes: `/` (HomePage), `/chat` (ChatPage), `/cart-confirmation` (CartConfirmation)
    - Create App.tsx with router and base layout
    - Set up global styles with Amazon brand palette (#232F3E primary, #FF9900 accent, 16px base spacing, system font stack)
    - _Requirements: 1.5_

  - [x] 11.2 Implement HomePage with category tiles
    - Create `src/pages/HomePage.tsx` and `src/components/CategoryTile.tsx`
    - Render exactly 5 category tiles: Grocery, Fashion, Tools, Electronics, Essentials with icons
    - On tile click: navigate to `/chat` with category as state/query param
    - Display voice CTA button: "Need something quickly? Talk to Amazon." below tiles, visible without scrolling on 360px+
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 11.3 Implement API service client
    - Create `src/services/api.ts` with axios/fetch wrapper
    - Implement functions: createSession, sendMessage, getRecommendations, addToCart
    - Handle error responses, extract correlation IDs
    - Implement retry logic: max 3 retries with exponential backoff (1s, 2s, 4s)
    - _Requirements: 20.1, 20.3_

  - [x] 11.4 Implement useSession hook
    - Create `src/hooks/useSession.ts`
    - Create session on first interaction (POST /sessions)
    - Store session ID in state, pass category if pre-selected from homepage
    - _Requirements: 4.1_

- [x] 12. Frontend conversational shopping screen
  - [x] 12.1 Implement ChatPage layout and state management
    - Create `src/pages/ChatPage.tsx`
    - Layout: chat thread area + text input + voice button at bottom
    - Initialize session on mount (with category if navigated from tile)
    - Manage messages array, loading state, connection status
    - _Requirements: 10.1_

  - [x] 12.2 Implement ChatThread and ChatBubble components
    - Create `src/components/ChatThread.tsx`: scrollable message list, auto-scroll to latest unless user scrolled up, show "new messages" indicator
    - Create `src/components/ChatBubble.tsx`: visually distinguish user vs agent messages (opposite sides or distinct styling)
    - _Requirements: 10.2, 10.3, 10.5_

  - [x] 12.3 Implement TextInput component and useChat hook
    - Create `src/components/TextInput.tsx`: text field (max 500 chars), send button, Enter key submit
    - Reject empty/whitespace-only submissions (keep input focused)
    - Create `src/hooks/useChat.ts`: send message, handle response, manage loading state
    - Disable input while processing (show LoadingIndicator), timeout at 30s
    - Preserve unsent message on error
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 10.4, 20.6_

  - [ ]* 12.4 Write property test for whitespace message rejection
    - **Property 1: Whitespace message rejection**
    - Generate strings of only whitespace characters, verify submission is rejected and state unchanged
    - Use fast-check library
    - **Validates: Requirements 3.3**

  - [ ]* 12.5 Write property test for session creation UUID v4
    - **Property 2: Session creation yields valid UUID v4**
    - Mock session creation responses, verify all session IDs match UUID v4 regex
    - Use fast-check library
    - **Validates: Requirements 4.1**

- [x] 13. Frontend product recommendations and cart
  - [x] 13.1 Implement RecommendationCard and ProductDetail components
    - Create `src/components/RecommendationCard.tsx`: product image, title, price, rating
    - Create `src/components/ProductDetail.tsx`: full details (image, title, brand, price, size, color, rating, "Add to Cart" button)
    - Render recommendation cards when agent response type is "recommendations"
    - Display explanation text from agent response
    - _Requirements: 8.2, 8.3, 8.4_

  - [x] 13.2 Implement cart operations and confirmation screen
    - Create `src/hooks/useCart.ts`: addToCart function with retry (3x)
    - Create `src/pages/CartConfirmation.tsx`: show added product, quantity, price, "Proceed to Checkout" CTA
    - Handle add-to-cart failure: show error, allow retry, suggest return to recommendations if product unavailable
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 14. Frontend voice integration
  - [x] 14.1 Implement Amazon Transcribe WebSocket client
    - Create `src/services/transcribe.ts`: WebSocket connection to Amazon Transcribe streaming API
    - Handle audio capture via Web Audio API / MediaRecorder
    - Stream audio chunks, receive partial and final transcription results
    - Handle connection failure: timeout after 5s, show error and enable text fallback
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 14.2 Implement VoiceButton component and useVoice hook
    - Create `src/components/VoiceButton.tsx`: pulsing animation during active listening, toggle start/stop
    - Create `src/hooks/useVoice.ts`: manage recording state, connect to Transcribe service
    - On stop (button press or 10s silence): submit transcribed text as message
    - Seamlessly switch between voice and text without losing context
    - _Requirements: 2.1, 2.5, 2.6, 10.4_

- [x] 15. Checkpoint - Full feature integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Error handling and resilience
  - [x] 16.1 Implement frontend error handling layer
    - Create connection-lost indicator (displayed within 2s of failure detection)
    - Implement auto-retry on connectivity restore (replay queued failed requests, max 3)
    - Ensure error messages are non-technical (no stack traces, service names, internal codes)
    - Handle rate limit (429): display "wait" message
    - _Requirements: 20.1, 20.3, 20.5_

  - [x] 16.2 Implement backend error handling and validation
    - Create error response format: `{error: {code, message, correlationId}}`
    - Implement request payload validation returning HTTP 400 with specific field errors
    - Handle DynamoDB 503 (5s timeout), Lambda 504 (29s), unhandled 502
    - Log full stack traces to CloudWatch on unhandled exceptions
    - _Requirements: 11.5, 12.3, 12.4, 12.5, 17.3, 20.2_

- [x] 17. AWS deployment configuration
  - [x] 17.1 Create SAM/CDK infrastructure template
    - Define DynamoDB table (`intentflow-sessions`) with TTL attribute, GSI for userId
    - Define Lambda function with FastAPI + Mangum, 29s timeout, appropriate memory
    - Define API Gateway REST API with routes and rate limiting (100 req/min/user)
    - Define S3 bucket for frontend static hosting (direct public access disabled)
    - Define CloudFront distribution with OAC, SPA fallback (index.html for all paths)
    - Define CloudWatch log groups with 14-day retention
    - Define S3 bucket for product catalog JSON
    - _Requirements: 12.1, 14.4, 16.1, 16.2, 16.3, 16.4, 17.4, 20.4_

  - [x] 17.2 Create deployment scripts
    - Frontend build and S3 sync script
    - CloudFront invalidation (/*) on deploy
    - Backend packaging and Lambda deployment
    - _Requirements: 16.3_

- [x] 18. Final checkpoint - Complete system
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Frontend uses TypeScript with fast-check for property tests
- Backend uses Python with Hypothesis for property tests
- For fastest demo: complete tasks 1-10 for backend, then 11-13 for frontend MVP, defer voice (14) and deployment (17) if time-constrained

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "5.1"] },
    { "id": 3, "tasks": ["2.3", "2.4", "3.2", "3.3", "4.1", "5.2"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.5", "4.6"] },
    { "id": 5, "tasks": ["4.4", "4.7", "4.8"] },
    { "id": 6, "tasks": ["7.1", "7.2"] },
    { "id": 7, "tasks": ["7.3", "8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3", "9.1"] },
    { "id": 9, "tasks": ["9.2", "9.3", "9.4", "9.5", "9.6", "9.7"] },
    { "id": 10, "tasks": ["9.8", "11.1"] },
    { "id": 11, "tasks": ["11.2", "11.3", "11.4"] },
    { "id": 12, "tasks": ["12.1"] },
    { "id": 13, "tasks": ["12.2", "12.3"] },
    { "id": 14, "tasks": ["12.4", "12.5", "13.1"] },
    { "id": 15, "tasks": ["13.2", "14.1"] },
    { "id": 16, "tasks": ["14.2", "16.1", "16.2"] },
    { "id": 17, "tasks": ["17.1"] },
    { "id": 18, "tasks": ["17.2"] }
  ]
}
```
