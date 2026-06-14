"""Environment configuration for IntentFlow backend."""

import os

from dotenv import load_dotenv

# Load .env file if present (local development)
load_dotenv()


class Settings:
    """Application settings loaded from environment variables with defaults."""

    # DynamoDB
    DYNAMODB_TABLE_NAME: str = os.getenv("DYNAMODB_TABLE_NAME", "intentflow-sessions")
    DYNAMODB_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    DYNAMODB_ENDPOINT_URL: str | None = os.getenv("DYNAMODB_ENDPOINT_URL", None)

    # Amazon Bedrock
    BEDROCK_MODEL_ID: str = os.getenv(
        "BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"
    )
    BEDROCK_REGION: str = os.getenv("BEDROCK_REGION", "us-east-1")

    # Intent Compression Engine
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.8"))
    MAX_QUESTIONS: int = int(os.getenv("MAX_QUESTIONS", "5"))

    # Rate Limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = int(
        os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "100")
    )

    # Rainforest API (real Amazon product search)
    RAINFOREST_API_KEY: str = os.getenv("RAINFOREST_API_KEY", "D6774401E3E44B6E93FAA1C93FDA45B1")
    AMAZON_DOMAIN: str = os.getenv("AMAZON_DOMAIN", "amazon.in")

    # Timeouts
    BEDROCK_TIMEOUT_SECONDS: int = int(os.getenv("BEDROCK_TIMEOUT_SECONDS", "15"))
    DYNAMODB_TIMEOUT_SECONDS: int = int(os.getenv("DYNAMODB_TIMEOUT_SECONDS", "5"))
    LAMBDA_TIMEOUT_SECONDS: int = int(os.getenv("LAMBDA_TIMEOUT_SECONDS", "29"))


settings = Settings()
