#!/bin/bash
set -e

# =============================================================================
# deploy-backend.sh — Build and deploy the IntentFlow backend to AWS Lambda
# =============================================================================

echo "=========================================="
echo "  IntentFlow Backend Deployment"
echo "=========================================="

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
INFRA_DIR="$PROJECT_ROOT/infrastructure"
BUILD_DIR="$PROJECT_ROOT/.build/backend"

# ---- Step 1: Clean and prepare build directory ----
echo ""
echo "[1/4] Preparing build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# ---- Step 2: Install Python dependencies into build directory ----
echo "[2/4] Installing Python dependencies..."
pip install -r "$BACKEND_DIR/requirements.txt" -t "$BUILD_DIR" --quiet
echo "       Dependencies installed to $BUILD_DIR"

# ---- Step 3: Package backend code ----
echo "[3/4] Packaging backend code..."
cp -r "$BACKEND_DIR"/*.py "$BUILD_DIR/" 2>/dev/null || true
cp -r "$BACKEND_DIR/routers" "$BUILD_DIR/" 2>/dev/null || true
cp -r "$BACKEND_DIR/services" "$BUILD_DIR/" 2>/dev/null || true
cp -r "$BACKEND_DIR/models" "$BUILD_DIR/" 2>/dev/null || true
cp -r "$BACKEND_DIR/middleware" "$BUILD_DIR/" 2>/dev/null || true
cp -r "$BACKEND_DIR/data" "$BUILD_DIR/" 2>/dev/null || true
echo "       Backend code packaged"

# ---- Step 4: SAM build and deploy ----
echo "[4/4] Running SAM build and deploy..."
cd "$INFRA_DIR"
sam build
echo ""
echo "       SAM build complete. Deploying..."
sam deploy --no-confirm-changeset --no-fail-on-empty-changeset
echo ""
echo "=========================================="
echo "  Backend deployment complete!"
echo "=========================================="
