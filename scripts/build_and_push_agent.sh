#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Build and Push FinTwit Agent Container Image to AWS ECR (ARM64)
# ==============================================================================

PROFILE="${1:-dev-admin}"
REGION="${AWS_REGION:-us-east-1}"
PROJECT="fintwit-rag"
ENV="dev"
IMAGE_TAG="${2:-latest}"

echo "==> Resolving AWS Account ID..."
ACCOUNT_ID=$(aws sts get-caller-identity --profile "$PROFILE" --query "Account" --output text)
ECR_REPO_NAME="${PROJECT}-${ENV}-agent"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
ECR_URI="${ECR_REGISTRY}/${ECR_REPO_NAME}:${IMAGE_TAG}"

echo "==> Ensuring ECR repository '${ECR_REPO_NAME}' exists..."
aws ecr describe-repositories --profile "$PROFILE" --region "$REGION" --repository-names "$ECR_REPO_NAME" >/dev/null 2>&1 || \
aws ecr create-repository --profile "$PROFILE" --region "$REGION" --repository-name "$ECR_REPO_NAME" >/dev/null

echo "==> Logging in to Amazon ECR (${ECR_REGISTRY})..."
aws ecr get-login-password --profile "$PROFILE" --region "$REGION" | \
docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "==> Building Docker image (linux/arm64) for ${ECR_URI}..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
AGENT_DIR="${REPO_ROOT}/lambdas/agent"

docker buildx build \
  --platform linux/arm64 \
  -t "${ECR_URI}" \
  -f "${AGENT_DIR}/Dockerfile" \
  "${AGENT_DIR}" \
  --push

echo "==> Successfully built and pushed ${ECR_URI}"
