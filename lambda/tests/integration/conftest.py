import os

import pytest


required = ["JINA_API_KEY", "QDRANT_URL", "COLLECTION_NAME"]
missing = [name for name in required if not os.getenv(name)]

provider = os.getenv("LLM_PROVIDER", "openai")
if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
    missing.append("OPENAI_API_KEY")

if missing:
    pytest.skip(f"Missing env vars for integration tests: {', '.join(sorted(set(missing)))}", allow_module_level=True)
