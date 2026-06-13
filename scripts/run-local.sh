#!/bin/bash
set -e

# =============================================================================
# run-local.sh — Start the IntentFlow backend locally for development
# =============================================================================

echo "=========================================="
echo "  IntentFlow Local Development"
echo "=========================================="

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---- Set local development environment variables ----
export USE_LOCAL_STORE=true
export USE_LOCAL_BEDROCK=true

echo ""
echo "  Environment:"
echo "    USE_LOCAL_STORE=$USE_LOCAL_STORE"
echo "    USE_LOCAL_BEDROCK=$USE_LOCAL_BEDROCK"
echo ""

# ---- Start backend with uvicorn ----
echo "[Backend] Starting uvicorn on http://localhost:8000 ..."
echo ""
echo "-------------------------------------------"
echo "  To start the frontend in another terminal:"
echo ""
echo "    cd frontend && npm run dev"
echo ""
echo "  The frontend dev server will run on http://localhost:5173"
echo "-------------------------------------------"
echo ""

cd "$PROJECT_ROOT"
uvicorn backend.main:app --reload --port 8000
