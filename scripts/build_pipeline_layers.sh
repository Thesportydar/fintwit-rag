#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Build the Lambda layers for the ingestion pipeline (python3.13 / arm64).
#
# Produces two zips (each must stay under the 50 MB direct-upload limit):
#   lambdas/pipeline_layer_arrow.zip  -> pyarrow
#   lambdas/pipeline_layer.zip        -> remaining dependencies
#
# boto3/botocore are excluded because the Lambda runtime already ships them.
# Requires: uv, docker, zip.
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REQ="${REPO_ROOT}/lambdas/pipeline/requirements.txt"
OUT_DIR="${REPO_ROOT}/lambdas"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

mkdir -p "${BUILD_DIR}/python"

echo "==> Installing dependencies for aarch64 / python3.13..."
uv pip install --target "${BUILD_DIR}/python" --python-platform aarch64-manylinux2014 \
  --python-version 3.13 --only-binary :all: -r "$REQ" >/dev/null

cd "${BUILD_DIR}/python"
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
find . -name "*.pyc" -delete
find . -type d \( -name tests -o -name test \) -prune -exec rm -rf {} +
rm -rf boto3* botocore* s3transfer*
rm -rf pyarrow/include pyarrow/src

echo "==> Stripping pyarrow shared objects (strip breaks numpy.libs, so only pyarrow)..."
docker run --rm --platform linux/arm64 -v "${BUILD_DIR}:/w" debian:bookworm-slim sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq binutils >/dev/null 2>&1 && find /w/python/pyarrow -name '*.so*' -type f -exec strip --strip-unneeded {} + 2>/dev/null"

cd "${BUILD_DIR}"
rm -f "${OUT_DIR}/pipeline_layer_arrow.zip" "${OUT_DIR}/pipeline_layer.zip"
zip -qr9 "${OUT_DIR}/pipeline_layer_arrow.zip" python/pyarrow python/pyarrow-*.dist-info
zip -qr9 "${OUT_DIR}/pipeline_layer.zip" python -x "python/pyarrow/*" "python/pyarrow-*.dist-info/*"

for z in pipeline_layer_arrow.zip pipeline_layer.zip; do
  size=$(wc -c < "${OUT_DIR}/${z}" | tr -d ' ')
  echo "==> ${z}: ${size} bytes"
  if [ "$size" -ge 52428800 ]; then
    echo "ERROR: ${z} exceeds the 50 MB direct-upload limit" >&2
    exit 1
  fi
done
