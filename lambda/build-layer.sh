#!/bin/bash
set -e

rm -rf python layer.zip
mkdir -p python

docker run --rm \
  --platform linux/amd64 \
  --entrypoint "" \
  --user 0:0 \
  -v "$PWD":/var/task \
  -w /var/task \
  public.ecr.aws/sam/build-python3.13 \
  bash -c "
    pip install --no-cache-dir --requirement requirements.txt --target python/
    rm -rf python/boto3* python/botocore* python/s3transfer*
    find python/ -type d -name '__pycache__' -exec rm -rf {} +
  "

zip -r layer.zip python
