#!/usr/bin/env bash
set -euo pipefail

# Creates minimal AWS resources for EC2 deployment.
# Required env vars:
# AWS_REGION, VPC_ID, SUBNET_ID, KEY_NAME
# Optional env vars:
# SECURITY_GROUP_NAME (default: cryptobot-sg)

: "${AWS_REGION:?Set AWS_REGION}"
: "${VPC_ID:?Set VPC_ID}"
: "${SUBNET_ID:?Set SUBNET_ID}"
: "${KEY_NAME:?Set KEY_NAME}"

SECURITY_GROUP_NAME="${SECURITY_GROUP_NAME:-cryptobot-sg}"

SG_ID=$(aws ec2 create-security-group \
  --group-name "$SECURITY_GROUP_NAME" \
  --description "CryptoBot paper trader" \
  --vpc-id "$VPC_ID" \
  --region "$AWS_REGION" \
  --query GroupId \
  --output text)

echo "Created security group: $SG_ID"

aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp \
  --port 22 \
  --cidr 0.0.0.0/0 \
  --region "$AWS_REGION" || true

aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp \
  --port 8080 \
  --cidr 0.0.0.0/0 \
  --region "$AWS_REGION" || true

echo "SG_ID=$SG_ID"
