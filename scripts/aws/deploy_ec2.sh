#!/usr/bin/env bash
set -euo pipefail

# Launches one EC2 instance and installs cryptobot from an uploaded tarball in S3.
# Required env vars:
# AWS_REGION, SUBNET_ID, SG_ID, KEY_NAME, INSTANCE_PROFILE_NAME, S3_BUCKET, S3_KEY
# Optional env vars:
# INSTANCE_TYPE (default t3.micro), AMI_ID

: "${AWS_REGION:?Set AWS_REGION}"
: "${SUBNET_ID:?Set SUBNET_ID}"
: "${SG_ID:?Set SG_ID}"
: "${KEY_NAME:?Set KEY_NAME}"
: "${INSTANCE_PROFILE_NAME:?Set INSTANCE_PROFILE_NAME}"
: "${S3_BUCKET:?Set S3_BUCKET}"
: "${S3_KEY:?Set S3_KEY}"

INSTANCE_TYPE="${INSTANCE_TYPE:-t3.micro}"
if [[ -z "${AMI_ID:-}" ]]; then
  if [[ "$INSTANCE_TYPE" == t4g* || "$INSTANCE_TYPE" == a1* ]]; then
    AMI_PARAM="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-arm64"
  else
    AMI_PARAM="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64"
  fi
  AMI_ID=$(aws ssm get-parameter \
    --name "$AMI_PARAM" \
    --region "$AWS_REGION" \
    --query 'Parameter.Value' \
    --output text)
fi

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
nohup python3 -m cryptobot.main >/var/log/cryptobot.log 2>&1 &
EOF

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --subnet-id "$SUBNET_ID" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name="$INSTANCE_PROFILE_NAME" \
  --user-data "file://$USER_DATA_FILE" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=cryptobot-paper}]' \
  --region "$AWS_REGION" \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "INSTANCE_ID=$INSTANCE_ID"
