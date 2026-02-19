#!/usr/bin/env bash
set -euo pipefail

# One-command deployment for CryptoBot on EC2.
# Creates or reuses:
# - S3 bucket for app bundle
# - IAM role + instance profile (S3 read + SSM)
# - Security group (port 8080 open, no SSH ingress)
# - EC2 instance in default VPC
#
# Optional env vars:
# AWS_PROFILE (default: default)
# AWS_REGION (default: us-east-1)
# APP_NAME (default: cryptobot-paper)
# INSTANCE_TYPE (default: t3.micro)
# S3_BUCKET (default: auto-generated)

AWS_PROFILE="${AWS_PROFILE:-default}"
AWS_REGION="${AWS_REGION:-us-east-1}"
APP_NAME="${APP_NAME:-cryptobot-paper}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.micro}"

ACCOUNT_ID=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
S3_BUCKET="${S3_BUCKET:-${APP_NAME}-${ACCOUNT_ID}-${AWS_REGION}}"
S3_KEY="cryptobot/app.tar.gz"
ROLE_NAME="${APP_NAME}-ec2-role"
PROFILE_NAME="${APP_NAME}-instance-profile"
SG_NAME="${APP_NAME}-sg"

echo "Using account: $ACCOUNT_ID"
echo "Using region:  $AWS_REGION"
echo "Using bucket:  $S3_BUCKET"

DEFAULT_VPC_ID=$(aws ec2 describe-vpcs \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' \
  --output text)

if [[ -z "$DEFAULT_VPC_ID" || "$DEFAULT_VPC_ID" == "None" ]]; then
  echo "No default VPC found in region $AWS_REGION."
  exit 1
fi

SUBNET_ID=$(aws ec2 describe-subnets \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --filters Name=vpc-id,Values="$DEFAULT_VPC_ID" \
  --query 'Subnets[0].SubnetId' \
  --output text)

if [[ -z "$SUBNET_ID" || "$SUBNET_ID" == "None" ]]; then
  echo "No subnet found in default VPC $DEFAULT_VPC_ID."
  exit 1
fi

if ! aws s3api head-bucket --profile "$AWS_PROFILE" --bucket "$S3_BUCKET" >/dev/null 2>&1; then
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --profile "$AWS_PROFILE" --bucket "$S3_BUCKET"
  else
    aws s3api create-bucket \
      --profile "$AWS_PROFILE" \
      --bucket "$S3_BUCKET" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION"
  fi
fi

TMP_BASE=$(mktemp /tmp/cryptobot-XXXXXX)
TMP_TAR="${TMP_BASE}.tar.gz"
tar -czf "$TMP_TAR" \
  --exclude='.git' \
  --exclude='state' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  -C "$(pwd)" .
aws s3 cp --profile "$AWS_PROFILE" "$TMP_TAR" "s3://${S3_BUCKET}/${S3_KEY}"

if ! aws iam get-role --profile "$AWS_PROFILE" --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role \
    --profile "$AWS_PROFILE" \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
      "Version":"2012-10-17",
      "Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]
    }' >/dev/null
fi

aws iam attach-role-policy \
  --profile "$AWS_PROFILE" \
  --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore >/dev/null
aws iam attach-role-policy \
  --profile "$AWS_PROFILE" \
  --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess >/dev/null

if ! aws iam get-instance-profile --profile "$AWS_PROFILE" --instance-profile-name "$PROFILE_NAME" >/dev/null 2>&1; then
  aws iam create-instance-profile --profile "$AWS_PROFILE" --instance-profile-name "$PROFILE_NAME" >/dev/null
  aws iam add-role-to-instance-profile \
    --profile "$AWS_PROFILE" \
    --instance-profile-name "$PROFILE_NAME" \
    --role-name "$ROLE_NAME" >/dev/null || true
  sleep 10
fi

SG_ID=$(aws ec2 describe-security-groups \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --filters Name=group-name,Values="$SG_NAME" Name=vpc-id,Values="$DEFAULT_VPC_ID" \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

if [[ -z "$SG_ID" || "$SG_ID" == "None" ]]; then
  SG_ID=$(aws ec2 create-security-group \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --group-name "$SG_NAME" \
    --description "Security group for ${APP_NAME}" \
    --vpc-id "$DEFAULT_VPC_ID" \
    --query GroupId \
    --output text)
fi

aws ec2 authorize-security-group-ingress \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-id "$SG_ID" \
  --protocol tcp \
  --port 8080 \
  --cidr 0.0.0.0/0 >/dev/null 2>&1 || true

if [[ "$INSTANCE_TYPE" == t4g* || "$INSTANCE_TYPE" == a1* ]]; then
  AMI_PARAM="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-arm64"
else
  AMI_PARAM="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64"
fi

AMI_ID=$(aws ssm get-parameter \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --name "$AMI_PARAM" \
  --query 'Parameter.Value' \
  --output text)

USER_DATA_FILE=$(mktemp)
cat > "$USER_DATA_FILE" <<EOF
#!/bin/bash
set -euo pipefail
yum update -y
yum install -y python3 tar
mkdir -p /opt/cryptobot
aws s3 cp s3://${S3_BUCKET}/${S3_KEY} /opt/cryptobot/app.tar.gz
cd /opt/cryptobot
tar -xzf app.tar.gz
cp -n .env.example .env || true
sed -i 's/^HOST=.*/HOST=0.0.0.0/' .env || true
nohup python3 -m cryptobot.main >/var/log/cryptobot.log 2>&1 &
EOF

INSTANCE_ID=$(aws ec2 run-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --subnet-id "$SUBNET_ID" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name="$PROFILE_NAME" \
  --associate-public-ip-address \
  --user-data "file://${USER_DATA_FILE}" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${APP_NAME}}]" \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "Launched instance: $INSTANCE_ID"
aws ec2 wait instance-status-ok --profile "$AWS_PROFILE" --region "$AWS_REGION" --instance-ids "$INSTANCE_ID"

PUBLIC_IP=$(aws ec2 describe-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

echo
echo "Deployment complete."
echo "Instance: $INSTANCE_ID"
echo "Public URL: http://${PUBLIC_IP}:8080"
echo "Health check: curl -s http://${PUBLIC_IP}:8080/api/status"
echo
echo "Cleanup when done:"
echo "aws ec2 terminate-instances --profile ${AWS_PROFILE} --region ${AWS_REGION} --instance-ids ${INSTANCE_ID}"
