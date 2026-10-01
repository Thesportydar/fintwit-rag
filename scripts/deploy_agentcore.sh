#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-${AWS_PROFILE:-}}"
REGION="${AWS_REGION:-us-east-1}"
RUNTIME_ID="${AGENTCORE_RUNTIME_ID:?Set AGENTCORE_RUNTIME_ID}"
IMAGE_URI="${AGENTCORE_IMAGE_URI:?Set AGENTCORE_IMAGE_URI}"
CLIENT_TOKEN="${AGENTCORE_CLIENT_TOKEN:-fintwit-agent-$(date +%s)-${RANDOM}}"

runtime_json="$(mktemp)"
update_json="$(mktemp)"
cleanup() {
  rm -f "$runtime_json" "$update_json"
}
trap cleanup EXIT

aws_args=(--region "$REGION")
if [[ -n "$PROFILE" ]]; then
  aws_args+=(--profile "$PROFILE")
fi

aws "${aws_args[@]}" bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id "$RUNTIME_ID" \
  --output json >"$runtime_json"

python3 - "$runtime_json" "$update_json" "$IMAGE_URI" "$CLIENT_TOKEN" <<'PY'
import json
import sys

source_path, target_path, image_uri, client_token = sys.argv[1:]
runtime = json.load(open(source_path, encoding="utf-8"))

payload = {
    "agentRuntimeId": runtime["agentRuntimeId"],
    "description": runtime.get("description", "FinTwit LangGraph RAG Agent Runtime"),
    "agentRuntimeArtifact": {
        "containerConfiguration": {
            "containerUri": image_uri,
        }
    },
    "roleArn": runtime["roleArn"],
    "networkConfiguration": runtime["networkConfiguration"],
    "protocolConfiguration": runtime["protocolConfiguration"],
    "environmentVariables": runtime.get("environmentVariables", {}),
    "authorizerConfiguration": runtime.get("authorizerConfiguration"),
    "clientToken": client_token,
}

if payload["authorizerConfiguration"] is None:
    payload.pop("authorizerConfiguration")

with open(target_path, "w", encoding="utf-8") as output:
    json.dump(payload, output)
PY

aws "${aws_args[@]}" bedrock-agentcore-control update-agent-runtime \
  --cli-input-json "file://$update_json" \
  --query '{Id:agentRuntimeId,Version:agentRuntimeVersion,Status:status}' \
  --output json

for _ in $(seq 1 30); do
  status="$(
    aws "${aws_args[@]}" bedrock-agentcore-control get-agent-runtime \
      --agent-runtime-id "$RUNTIME_ID" \
      --query status \
      --output text
  )"
  case "$status" in
    READY)
      exit 0
      ;;
    FAILED)
      echo "AgentCore runtime update failed." >&2
      exit 1
      ;;
  esac
  sleep 10
done

echo "Timed out waiting for AgentCore runtime to become READY." >&2
exit 1
