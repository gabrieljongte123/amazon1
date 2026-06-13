#!/bin/bash
set -e

# =============================================================================
# setup.sh — Set up the IntentFlow development environment
# =============================================================================

echo "=========================================="
echo "  IntentFlow Development Setup"
echo "=========================================="

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---- Step 1: Install backend dependencies ----
echo ""
echo "[1/3] Installing backend Python dependencies..."
pip install -r "$PROJECT_ROOT/backend/requirements.txt"
echo "       Backend dependencies installed"

# ---- Step 2: Install frontend dependencies ----
echo "[2/3] Installing frontend Node.js dependencies..."
cd "$PROJECT_ROOT/frontend" && npm install
echo "       Frontend dependencies installed"

# ---- Step 3: Create .env file with defaults ----
echo "[3/3] Creating .env file with local development defaults..."
ENV_FILE="$PROJECT_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
  echo "       .env file already exists — skipping (delete it to regenerate)"
else
  cat > "$ENV_FILE" <<EOF
# =============================================================================
# IntentFlow — Local Development Environment Configuration
# =============================================================================

# Backend settings
USE_LOCAL_STORE=true
USE_LOCAL_BEDROCK=true
DYNAMODB_TABLE_NAME=intentflow-sessions
BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
BEDROCK_REGION=us-east-1
CONFIDENCE_THRESHOLD=0.8
MAX_QUESTIONS=5

# Frontend settings (used by Vite via import.meta.env)
VITE_API_BASE_URL=http://localhost:8000

# AWS settings (only needed for deployment, not local dev)
# AWS_REGION=us-east-1
# FRONTEND_S3_BUCKET=intentflow-frontend-<account-id>
# CLOUDFRONT_DISTRIBUTION_ID=<distribution-id>
EOF
  echo "       .env file created at $ENV_FILE"
fi

echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo ""
echo "  Next steps:"
echo "    1. Run the backend:   ./scripts/run-local.sh"
echo "    2. Run the frontend:  cd frontend && npm run dev"
echo ""
