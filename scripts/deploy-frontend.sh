#!/bin/bash
set -e

# =============================================================================
# deploy-frontend.sh — Build and deploy the IntentFlow frontend to S3/CloudFront
# =============================================================================

echo "=========================================="
echo "  IntentFlow Frontend Deployment"
echo "=========================================="

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# These can be overridden via environment variables
S3_BUCKET="${FRONTEND_S3_BUCKET:-}"
CLOUDFRONT_DISTRIBUTION_ID="${CLOUDFRONT_DISTRIBUTION_ID:-}"

# ---- Validate required environment variables ----
if [ -z "$S3_BUCKET" ]; then
  echo "ERROR: FRONTEND_S3_BUCKET environment variable is not set."
  echo "       Set it to your S3 bucket name, e.g.:"
  echo "       export FRONTEND_S3_BUCKET=intentflow-frontend-123456789012"
  exit 1
fi

if [ -z "$CLOUDFRONT_DISTRIBUTION_ID" ]; then
  echo "ERROR: CLOUDFRONT_DISTRIBUTION_ID environment variable is not set."
  echo "       Set it to your CloudFront distribution ID, e.g.:"
  echo "       export CLOUDFRONT_DISTRIBUTION_ID=E1A2B3C4D5E6F7"
  exit 1
fi

# ---- Step 1: Build the frontend ----
echo ""
echo "[1/3] Building frontend..."
cd "$FRONTEND_DIR"
npm run build
echo "       Build complete (dist/ directory ready)"

# ---- Step 2: Sync to S3 ----
echo "[2/3] Syncing dist/ to S3 bucket: $S3_BUCKET..."
aws s3 sync "$FRONTEND_DIR/dist/" "s3://$S3_BUCKET" --delete
echo "       S3 sync complete"

# ---- Step 3: Invalidate CloudFront cache ----
echo "[3/3] Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
  --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
  --paths "/*" \
  --output text
echo "       Cache invalidation initiated"

echo ""
echo "=========================================="
echo "  Frontend deployment complete!"
echo "=========================================="
echo ""
echo "  Your site will be available at your CloudFront URL"
echo "  once the cache invalidation finishes (usually 1-2 minutes)."
