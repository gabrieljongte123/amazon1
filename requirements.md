# Requirements Document

## Introduction

IntentFlow is an AI-driven conversational commerce experience for Amazon Now (quick-commerce). It replaces the traditional browse-filter-compare shopping flow with a progressive intent narrowing conversation. An AI agent asks the minimum number of questions required to understand the customer's need and deliver product recommendations, reducing shopping time from minutes to seconds. The system supports both voice and text input and is built on AWS serverless infrastructure.

## Glossary

- **IntentFlow_Agent**: The AI-powered conversational agent that processes user input, extracts intent, determines missing attributes, and generates the next best question or product recommendations.
- **Intent_Compression_Engine**: The core algorithm that minimizes the number of questions before recommending products by maximizing information gain per question and tracking confidence scores.
- **Session**: A bounded conversation between a single user and the IntentFlow_Agent, identified by a unique session ID, containing all context accumulated during the interaction.
- **Confidence_Score**: A numeric value between 0.0 and 1.0 representing how certain the Intent_Compression_Engine is that it has enough information to recommend products.
- **Confidence_Threshold**: The minimum Confidence_Score (configurable, default 0.8) at which the Intent_Compression_Engine stops asking questions and generates recommendations.
- **Information_Gain**: A measure of how much a particular question reduces uncertainty about the user's intent, used to select the next best question.
- **Attribute**: A specific piece of information about the user's desired product (e.g., category, brand, price range, size, color).
- **Frontend_App**: The React-based web application that provides the user interface for the conversational shopping experience.
- **API_Gateway**: The Amazon API Gateway layer that routes client requests to backend services.
- **Session_Store**: The DynamoDB table that persists session state and conversation context.
- **Product_Catalog**: The mock JSON data source containing product information used for recommendations.
- **Voice_Service**: The integration with Amazon Transcribe that converts user speech to text.
- **Recommendation_Card**: A UI component displaying a single product recommendation with image, title, price, and rating.

## Requirements

### Requirement 1: Homepage Display

**User Story:** As a customer, I want to see a visually appealing homepage with category tiles, so that I can quickly understand what products are available and begin my shopping experience.

#### Acceptance Criteria

1. WHEN the customer navigates to the application root URL, THE Frontend_App SHALL display the homepage with exactly 5 category tiles: Grocery, Fashion, Tools, Electronics, and Essentials, each showing a category name and representative icon.
2. THE Frontend_App SHALL display a voice activation button with the label "Need something quickly? Talk to Amazon." positioned prominently below the category tiles and visible without scrolling on standard viewport sizes (360px width and above).
3. WHEN the customer selects a category tile, THE Frontend_App SHALL navigate to the conversational shopping screen with the selected category pre-filled as the first known Attribute in the Session context.
4. THE Frontend_App SHALL render the homepage within 2 seconds of initial page load on a standard broadband connection.
5. THE Frontend_App SHALL render the homepage using Amazon's brand color palette (#232F3E primary, #FF9900 accent) with consistent 16px base spacing and system font stack.

### Requirement 2: Voice Input Activation

**User Story:** As a customer, I want to use my voice to describe what I need, so that I can communicate my intent faster than typing.

#### Acceptance Criteria

1. WHEN the customer presses the voice activation button, THE Frontend_App SHALL display a visual voice activation state with a pulsing animation indicating active listening within 200ms of button press.
2. WHILE the voice activation state is active, THE Voice_Service SHALL stream audio input to Amazon Transcribe for real-time speech-to-text conversion using the WebSocket streaming API.
3. WHEN Amazon Transcribe returns a final transcription result, THE Voice_Service SHALL pass the transcribed text to the IntentFlow_Agent as user input and display the transcribed text in the chat thread.
4. IF the Voice_Service fails to connect to Amazon Transcribe within 5 seconds, THEN THE Frontend_App SHALL display an error message stating "Voice is unavailable. Please type your request." and enable the text input field as a fallback.
5. WHEN the customer presses the voice activation button again during active listening, THE Frontend_App SHALL stop the voice recording and submit the captured transcription as a complete user message.
6. IF no speech is detected for 10 seconds during active listening, THEN THE Voice_Service SHALL automatically stop recording and notify the customer that no input was detected.

### Requirement 3: Text-Based Conversational Input

**User Story:** As a customer, I want to type my needs in natural language, so that I can interact with the agent without using voice.

#### Acceptance Criteria

1. THE Frontend_App SHALL display a text input field on the conversational shopping screen for typed natural language input, with a maximum length of 500 characters.
2. WHEN the customer submits a text message by pressing the Enter key or activating the send button, THE Frontend_App SHALL send the message to the IntentFlow_Agent for processing.
3. IF the customer attempts to submit an empty or whitespace-only message, THEN THE Frontend_App SHALL not send the message and SHALL keep the input field focused.
4. WHILE the IntentFlow_Agent is processing the message, THE Frontend_App SHALL display a loading indicator and disable the text input field until a response is received or a timeout of 30 seconds is reached.
5. THE Frontend_App SHALL display the conversation history for the current Session as a scrollable chat thread showing both user messages and agent responses.

### Requirement 4: Session Creation and Management

**User Story:** As a customer, I want my conversation context to be maintained throughout my shopping session, so that the agent remembers what I have already communicated.

#### Acceptance Criteria

1. WHEN a customer initiates a new conversation, THE API_Gateway SHALL create a new Session with a unique session ID (UUID v4) and return the session ID to the Frontend_App.
2. THE Session_Store SHALL persist the session state including conversation history (up to 100 messages per session), extracted attributes, and Confidence_Score for each active Session.
3. WHEN the customer sends a message, THE API_Gateway SHALL validate that the provided session ID corresponds to an existing, non-expired Session and associate the message with the correct Session context.
4. IF the Session_Store does not respond within 5 seconds, THEN THE API_Gateway SHALL return an error response with HTTP status 503 and a message indicating temporary unavailability.
5. IF a request includes a session ID that does not exist or has expired, THEN THE API_Gateway SHALL return an error response with HTTP status 404 and a message indicating the session was not found.

### Requirement 5: Intent Extraction from Natural Language

**User Story:** As a customer, I want the agent to understand my natural language input, so that I do not need to use specific keywords or navigation structures.

#### Acceptance Criteria

1. WHEN a user message is received, THE IntentFlow_Agent SHALL extract all identifiable Attributes (category, brand, price range, size, color, and other product-relevant properties) from the natural language input using Amazon Bedrock (Claude) and store them in the Session.
2. WHEN the IntentFlow_Agent extracts an Attribute that conflicts with a previously stored Attribute in the Session (e.g., a new color replacing a prior color), THE IntentFlow_Agent SHALL replace the previous value with the newly extracted value.
3. WHEN a user message is received, THE IntentFlow_Agent SHALL merge newly extracted Attributes with the Session's existing known Attributes, preserving previously known Attributes that are not contradicted by the new message.
4. IF the IntentFlow_Agent cannot extract at least one product-related Attribute from the user message, THEN THE IntentFlow_Agent SHALL ask a clarifying question that guides the user toward providing a product category, use case, or preference.
5. IF the IntentFlow_Agent has asked 3 consecutive clarifying questions without extracting any new Attribute, THEN THE IntentFlow_Agent SHALL present the available product categories and invite the user to select one.

### Requirement 6: Intent Compression Engine - Next Question Selection

**User Story:** As a customer, I want the agent to ask only the most relevant questions, so that I reach my desired product with minimum effort.

#### Acceptance Criteria

1. WHEN the IntentFlow_Agent has processed a user message and the Confidence_Score is below the Confidence_Threshold, THE Intent_Compression_Engine SHALL determine the missing Attributes and select the next question that maximizes Information_Gain. IF the product category has not yet been identified, THE Intent_Compression_Engine SHALL prioritize determining the category before selecting other Attributes.
2. THE Intent_Compression_Engine SHALL calculate the Confidence_Score based on the ratio of known Attributes to required Attributes for the identified product category, where required Attributes are defined per category in the Product_Catalog schema.
3. WHEN a user answers a question, THE Intent_Compression_Engine SHALL update the Confidence_Score to reflect the newly known Attribute.
4. THE Intent_Compression_Engine SHALL prioritize Attributes in order of discriminative power within the product category (Attributes that eliminate the most products are asked first).
5. THE Intent_Compression_Engine SHALL generate natural-sounding questions using conversational language via the Amazon Bedrock prompt rather than structured form-like prompts.
6. THE Intent_Compression_Engine SHALL NOT ask more than 5 questions in a single session before triggering product recommendation retrieval, regardless of the Confidence_Score.

### Requirement 7: Confidence-Based Recommendation Trigger

**User Story:** As a customer, I want the agent to recommend products as soon as it has enough information, so that I am not asked unnecessary questions.

#### Acceptance Criteria

1. WHEN the Confidence_Score reaches or exceeds the Confidence_Threshold, THE Intent_Compression_Engine SHALL stop generating questions and trigger product recommendation retrieval.
2. THE Intent_Compression_Engine SHALL use a default Confidence_Threshold of 0.8.
3. IF the Product_Catalog contains fewer than 4 matching products for the known Attributes before reaching the Confidence_Threshold, THEN THE Intent_Compression_Engine SHALL trigger product recommendation retrieval early without asking additional questions.
4. WHEN the user explicitly requests recommendations (e.g., "show me what you have", "just recommend something"), THE Intent_Compression_Engine SHALL trigger product recommendation retrieval regardless of the current Confidence_Score.
5. IF the Product_Catalog returns zero matching products after recommendation retrieval is triggered, THEN THE IntentFlow_Agent SHALL inform the customer that no products match the current criteria and suggest broadening preferences by relaxing one or more Attributes.

### Requirement 8: Product Recommendation Display

**User Story:** As a customer, I want to see relevant product recommendations with key details, so that I can make a quick purchase decision.

#### Acceptance Criteria

1. WHEN product recommendations are triggered, THE IntentFlow_Agent SHALL retrieve products from the Product_Catalog that match all known Attributes and return up to 5 products sorted by customer rating in descending order (highest-rated first).
2. WHEN the Frontend_App receives product recommendations from the IntentFlow_Agent, THE Frontend_App SHALL display each recommended product as a Recommendation_Card containing the product image, title, price, and customer rating.
3. WHEN the customer selects a recommended product, THE Frontend_App SHALL display the product detail view including image, title, brand, price, size (where applicable), color (where applicable), customer rating, and an "Add to Cart" button.
4. WHEN the IntentFlow_Agent presents recommendations, THE IntentFlow_Agent SHALL include an explanation of no more than 2 sentences referencing the known Attributes used to filter the recommendations (e.g., "Based on your preference for Converse sneakers under ₹3000 in size 8").
5. IF the Product_Catalog returns zero matching products for the known Attributes, THEN THE IntentFlow_Agent SHALL inform the customer that no products match the current criteria and suggest broadening preferences by relaxing one or more Attributes.

### Requirement 9: Add to Cart

**User Story:** As a customer, I want to add a recommended product to my cart directly from the conversation, so that I can complete my purchase without navigating away.

#### Acceptance Criteria

1. WHEN the customer confirms a product selection (via text, voice, or button click), THE Frontend_App SHALL send an add-to-cart request to the API_Gateway containing the product ID and a quantity of 1.
2. WHEN an add-to-cart request is received, THE API_Gateway SHALL add the specified product to the customer's cart and return a success confirmation including the product ID, quantity, and current cart item count.
3. WHEN the API_Gateway returns a successful add-to-cart confirmation, THE Frontend_App SHALL display a cart confirmation screen showing the added product, quantity, price, and a "Proceed to Checkout" call-to-action.
4. IF the add-to-cart operation fails, THEN THE Frontend_App SHALL display an error message indicating the product could not be added and allow the customer to retry up to 3 times.
5. IF the specified product is unavailable in the Product_Catalog at the time of the add-to-cart request, THEN THE API_Gateway SHALL return an error response indicating the product is unavailable, and THE Frontend_App SHALL inform the customer and suggest returning to recommendations.

### Requirement 10: Conversational Shopping Screen

**User Story:** As a customer, I want a dedicated conversational interface that feels natural and responsive, so that my shopping experience feels like a real conversation.

#### Acceptance Criteria

1. THE Frontend_App SHALL display the conversational shopping screen with the chat thread, text input, and voice activation button.
2. WHEN the IntentFlow_Agent sends a response, THE Frontend_App SHALL render the response as visible in the chat thread within 500ms of receiving the API response.
3. WHEN a new message is added to the chat thread (from the user or the IntentFlow_Agent), THE Frontend_App SHALL auto-scroll the chat thread to the latest message, unless the user has manually scrolled up, in which case the Frontend_App SHALL display an indicator showing new messages are available below.
4. THE Frontend_App SHALL support switching between voice and text input at any point in the conversation while preserving the full conversation history, all extracted Attributes in the Session, and any text currently entered in the input field.
5. THE Frontend_App SHALL visually distinguish user messages from IntentFlow_Agent messages in the chat thread by displaying them on opposite sides or with distinct visual styling.

### Requirement 11: Backend API Layer

**User Story:** As a developer, I want well-defined API endpoints for session management, intent processing, and cart operations, so that the frontend can communicate reliably with backend services.

#### Acceptance Criteria

1. THE API_Gateway SHALL expose a POST /sessions endpoint that creates a new Session and returns the session ID.
2. THE API_Gateway SHALL expose a POST /sessions/{sessionId}/messages endpoint that accepts a request body containing a text field with the user message and returns the IntentFlow_Agent response.
3. THE API_Gateway SHALL expose a GET /sessions/{sessionId}/recommendations endpoint that returns product recommendations for the current session state.
4. THE API_Gateway SHALL expose a POST /cart/items endpoint that accepts a request body containing a product ID and a quantity (integer, minimum 1, maximum 10) and adds the specified product to the customer's cart.
5. THE API_Gateway SHALL validate all incoming request payloads for required fields and correct data types, and return HTTP 400 with an error message indicating which validation rule failed for requests that do not conform.
6. IF a request references a session ID that does not exist or has expired, THEN THE API_Gateway SHALL return HTTP 404 with an error message indicating the session was not found.

### Requirement 12: AWS Lambda Compute

**User Story:** As a developer, I want the backend logic to run on serverless compute, so that the system scales automatically and minimizes infrastructure cost.

#### Acceptance Criteria

1. WHEN the API_Gateway receives a request matching a defined endpoint (POST /sessions, POST /sessions/{sessionId}/messages, GET /sessions/{sessionId}/recommendations, POST /cart/items), THE API_Gateway SHALL route the request to the corresponding AWS Lambda function for processing.
2. THE AWS Lambda functions SHALL use the FastAPI framework for request handling and response generation.
3. IF a Lambda function execution exceeds 29 seconds, THEN THE API_Gateway SHALL return an HTTP 504 timeout response to the client.
4. THE AWS Lambda functions SHALL log request and response metadata to Amazon CloudWatch for each invocation, including session ID (where applicable), request type, response status, and response latency in milliseconds.
5. IF a Lambda function encounters an unhandled execution error, THEN THE API_Gateway SHALL return an HTTP 502 response to the client with an error message indicating a processing failure.

### Requirement 13: Amazon Bedrock Integration

**User Story:** As a developer, I want to leverage Amazon Bedrock with Claude for natural language understanding and response generation, so that the agent can handle diverse user inputs intelligently.

#### Acceptance Criteria

1. WHEN the IntentFlow_Agent processes a user message, THE IntentFlow_Agent SHALL invoke Amazon Bedrock (Claude) with the conversation context and the user message to generate a response, with a timeout of 15 seconds per invocation.
2. THE IntentFlow_Agent SHALL include the session's known Attributes and conversation history (last 20 messages) in the prompt sent to Amazon Bedrock.
3. IF Amazon Bedrock returns an error or does not respond within 15 seconds, THEN THE IntentFlow_Agent SHALL retry once, and if the retry also fails, return a message to the user stating "I'm having trouble processing your request right now. Please try again in a moment."
4. THE IntentFlow_Agent SHALL include a system prompt that constrains Bedrock responses to shopping-related topics. IF the user sends an off-topic message, THEN THE IntentFlow_Agent SHALL respond with a single-sentence redirect guiding the customer back to a shopping-related topic.
5. THE IntentFlow_Agent SHALL NOT forward any Bedrock response that does not relate to shopping assistance, product discovery, or the current conversational context.

### Requirement 14: DynamoDB Session Persistence

**User Story:** As a developer, I want session data persisted in DynamoDB, so that conversations survive Lambda cold starts and can be resumed.

#### Acceptance Criteria

1. WHEN a new Session is created, THE Session_Store SHALL write a new item to DynamoDB with the session ID as the partition key.
2. WHEN the IntentFlow_Agent updates session state (new Attributes, updated Confidence_Score, new messages), THE Session_Store SHALL update the corresponding DynamoDB item and set the last updated timestamp to the current time.
3. THE Session_Store SHALL store the following fields for each session: session ID, conversation history (maximum 50 messages), extracted Attributes, Confidence_Score, created timestamp, and last updated timestamp.
4. WHEN a session has not been updated for 30 minutes, THE Session_Store SHALL consider the session expired and allow the record to be cleaned up via DynamoDB TTL.
5. WHEN a session ID is provided for retrieval, THE Session_Store SHALL return all stored fields for the corresponding DynamoDB item.
6. IF a DynamoDB write or update operation fails, THEN THE Session_Store SHALL propagate the error to the calling service without modifying the existing session state.
7. IF a retrieval request references a session ID that does not exist or has been removed by TTL, THEN THE Session_Store SHALL return a "session not found" indication to the calling service.

### Requirement 15: Product Catalog Data

**User Story:** As a developer, I want a mock product catalog with realistic data, so that the recommendation engine can demonstrate meaningful product matching.

#### Acceptance Criteria

1. THE Product_Catalog SHALL contain mock product data for the categories: Grocery, Fashion, Tools, Electronics, and Essentials.
2. THE Product_Catalog SHALL store each product with the following fields: product ID, title, category, brand, price, size (where applicable), color (where applicable), rating (a numeric value from 1.0 to 5.0 in 0.1 increments), image URL, and searchable Attributes (key-value pairs representing filterable product characteristics such as size, color, brand, and price range).
3. THE Product_Catalog SHALL contain a minimum of 10 products per category to enable meaningful recommendation filtering.
4. WHEN the IntentFlow_Agent queries the Product_Catalog with known Attributes, THE Product_Catalog SHALL return all products where each specified categorical Attribute (category, brand, color, size) exactly matches the product's corresponding field, and each specified numeric Attribute (price) falls within the requested range.
5. IF the IntentFlow_Agent queries the Product_Catalog and no products match the specified Attributes, THEN THE Product_Catalog SHALL return an empty result set.

### Requirement 16: Static Hosting and CDN

**User Story:** As a developer, I want the frontend hosted on S3 with CloudFront, so that the application loads quickly for customers.

#### Acceptance Criteria

1. THE Frontend_App SHALL be deployed as static assets to an Amazon S3 bucket configured for static web hosting with direct public access disabled.
2. THE Frontend_App SHALL be served through Amazon CloudFront using an Origin Access Control policy that restricts content delivery exclusively through the CloudFront distribution.
3. WHEN the Frontend_App is deployed, THE deployment process SHALL invalidate all CloudFront cached paths (/*) to ensure customers receive the latest version.
4. IF a request is made to a URL path that does not match a static asset file, THEN THE CloudFront distribution SHALL return the index.html file to support client-side routing in the React single-page application.

### Requirement 17: Monitoring and Observability

**User Story:** As a developer, I want monitoring and logging for all backend services, so that I can diagnose issues and understand system behavior.

#### Acceptance Criteria

1. THE AWS Lambda functions SHALL emit structured JSON logs to Amazon CloudWatch including session ID, request type, response latency in milliseconds, and a unique request correlation ID for cross-service tracing.
2. THE API_Gateway SHALL log all API requests with HTTP method, path, status code, response time in milliseconds, and the request correlation ID to CloudWatch.
3. IF a Lambda function throws an unhandled exception, THEN THE monitoring system SHALL log the full error stack trace to CloudWatch along with the session ID and request correlation ID.
4. THE CloudWatch log groups SHALL be configured with a retention period of 14 days.

### Requirement 18: Authentication (Prototype)

**User Story:** As a developer, I want a simplified mock authentication mechanism, so that the prototype can associate sessions with users without implementing full auth.

#### Acceptance Criteria

1. THE API_Gateway SHALL accept a mock user identifier in the request headers (X-User-Id) as a non-empty string of maximum 64 characters to associate sessions with users.
2. IF a request lacks the X-User-Id header, THEN THE API_Gateway SHALL generate a temporary anonymous user identifier (UUID v4), return it in the X-User-Id response header, and associate it with the Session for the duration of the session.
3. THE Session_Store SHALL associate each Session with the user identifier, enabling retrieval of all Sessions for a given user identifier.
4. IF the X-User-Id header is present but contains an empty string or exceeds 64 characters, THEN THE API_Gateway SHALL return HTTP 400 with an error message indicating an invalid user identifier format.

### Requirement 19: Agent Response Formatting

**User Story:** As a customer, I want agent responses to be conversational and friendly, so that the interaction feels natural rather than robotic.

#### Acceptance Criteria

1. THE IntentFlow_Agent SHALL generate responses using first-person language, contractions, and plain vocabulary without technical jargon or system-internal terminology.
2. WHEN presenting options to the customer, THE IntentFlow_Agent SHALL format choices as a numbered list containing no more than 5 items, with each item described in no more than 10 words.
3. THE IntentFlow_Agent SHALL keep question responses to a maximum of 2 sentences and non-question responses (acknowledgments, explanations, transitions) to a maximum of 3 sentences.
4. WHEN the IntentFlow_Agent presents product recommendations, THE IntentFlow_Agent SHALL summarize the top recommendation in no more than 2 sentences including the product title and price, and ask if the customer wants to proceed or see alternatives.
5. IF the IntentFlow_Agent receives input it cannot address within the shopping domain, THEN THE IntentFlow_Agent SHALL respond with a single-sentence redirect guiding the customer back to a shopping-related topic.

### Requirement 20: Error Handling and Resilience

**User Story:** As a customer, I want the system to handle errors gracefully, so that my shopping experience is not disrupted by technical issues.

#### Acceptance Criteria

1. IF any backend service returns an error, THEN THE Frontend_App SHALL display a non-technical error message indicating the operation could not be completed, without exposing stack traces, service names, or internal error codes.
2. IF the IntentFlow_Agent fails to process a message after one retry with a timeout of 5 seconds per attempt, THEN THE IntentFlow_Agent SHALL inform the customer that the message could not be understood and suggest rephrasing the input.
3. WHEN a network request from the Frontend_App fails due to connectivity issues, THE Frontend_App SHALL display a "Connection lost" indicator within 2 seconds of failure detection and automatically retry the failed request up to 3 times when connectivity is restored.
4. THE API_Gateway SHALL implement request rate limiting of 100 requests per minute per user to protect backend services from overload.
5. IF a user exceeds the rate limit of 100 requests per minute, THEN THE API_Gateway SHALL reject the request with HTTP status 429 and THE Frontend_App SHALL display a message indicating the customer should wait before trying again.
6. IF an error occurs during message submission, THEN THE Frontend_App SHALL preserve the customer's unsent message in the text input field so the customer can resubmit without retyping.
