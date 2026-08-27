#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "[BUILD] Construyendo Layers optimizadas (< 50MB)"
echo "=========================================="

# 1. Build Agent Layer
echo "=== 1. Building Agent Layer ==="
rm -rf python agent_layer.zip
mkdir -p python

docker run --rm \
  --platform linux/arm64 \
  --entrypoint "" \
  --user 0:0 \
  -v "$SCRIPT_DIR/agent":/var/src:ro \
  -v "$SCRIPT_DIR":/var/task \
  -w /var/task \
  public.ecr.aws/sam/build-python3.13:latest-arm64 \
  bash -c "
    pip install --no-cache-dir --requirement /var/src/requirements.txt --target python/
    rm -rf python/boto3* python/botocore* python/s3transfer*
    rm -rf python/numpy/tests python/numpy/typing/tests
    find python/ -type d -name '__pycache__' -exec rm -rf {} +
  "

zip -9 -r agent_layer.zip python
rm -rf python

# 2. Build Pipeline Layer
echo "=== 2. Building Pipeline Layer ==="
rm -rf python pipeline_layer.zip
mkdir -p python

docker run --rm \
  --platform linux/arm64 \
  --entrypoint "" \
  --user 0:0 \
  -v "$SCRIPT_DIR/pipeline":/var/src:ro \
  -v "$SCRIPT_DIR":/var/task \
  -w /var/task \
  public.ecr.aws/sam/build-python3.13:latest-arm64 \
  bash -c "
    pip install --no-cache-dir --requirement /var/src/requirements.txt --target python/
    rm -rf python/boto3* python/botocore* python/s3transfer*
    rm -rf python/grpc* python/google*
    rm -rf python/numpy/tests python/numpy/typing/tests
    rm -rf python/pyarrow/include python/pyarrow/tests python/pyarrow/src python/pyarrow/includes
    rm -rf python/pyarrow/libarrow_flight* python/pyarrow/libarrow_substrait* python/pyarrow/libarrow_acero* python/pyarrow/libarrow_dataset*
    rm -rf python/pyarrow/_flight* python/pyarrow/_gcsfs* python/pyarrow/_azurefs* python/pyarrow/_hdfs* python/pyarrow/_cuda* python/pyarrow/_orc* python/pyarrow/_dataset_orc* python/pyarrow/_substrait*
    find python/ -type d -name '__pycache__' -exec rm -rf {} +
    find python/pyarrow -name '*.pyx' -o -name '*.pxd' -o -name '*.pxi' -o -name '*.h' -o -name '*.cc' -o -name '*.cpp' -o -name '*.c' | xargs rm -rf 2>/dev/null || true
  "

zip -9 -r pipeline_layer.zip python
rm -rf python

echo "=========================================="
echo "[OK] Layers generadas con éxito en lambdas/ (< 50MB):"
echo "=========================================="
ls -lh agent_layer.zip pipeline_layer.zip
