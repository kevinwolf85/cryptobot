#!/usr/bin/env bash
set -euo pipefail

# Packages local source and uploads to S3.
# Required env vars:
# S3_BUCKET
# Optional env vars:
# S3_KEY (default: cryptobot/app.tar.gz)

: "${S3_BUCKET:?Set S3_BUCKET}"
S3_KEY="${S3_KEY:-cryptobot/app.tar.gz}"

WORKDIR=$(pwd)
TMP_BASE=$(mktemp /tmp/cryptobot-XXXXXX)
TMP_TAR="${TMP_BASE}.tar.gz"

tar -czf "$TMP_TAR" \
  --exclude='.git' \
  --exclude='state' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  -C "$WORKDIR" .

aws s3 cp "$TMP_TAR" "s3://${S3_BUCKET}/${S3_KEY}"
echo "Uploaded s3://${S3_BUCKET}/${S3_KEY}"
