#!/bin/bash
set -e
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

if [ -z "${AWS_DEFAULT_REGION}" ]; then
    echo "Define env variable AWS_DEFAULT_REGION (should be your region name, ex: us-east-1) and try again."
    exit 1
fi

export TF_ENVIRONMENT_ID="${AWS_ACCOUNT_ID}-${AWS_DEFAULT_REGION}"
HASH_COMMAND=${HASH_COMMAND:-sha1sum}
HASHED_ENVIRONMENT_ID=$(echo -n ${TF_ENVIRONMENT_ID} | "${HASH_COMMAND}" | awk '{print $1}')

cat <<EOF > backend.tf
terraform {
  backend "s3" {
    bucket         = "terraform-state-${HASHED_ENVIRONMENT_ID}"
    key            = "terraform/main/main.tfstate"
    region         = "${AWS_DEFAULT_REGION}"
    encrypt        = true
    dynamodb_table = "terraform-state-lock-${HASHED_ENVIRONMENT_ID}"
  }
}
EOF
