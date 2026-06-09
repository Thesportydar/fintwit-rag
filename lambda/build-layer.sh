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
  "

zip -r layer.zip python
