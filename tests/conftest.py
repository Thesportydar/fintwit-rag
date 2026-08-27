import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

# Asegurar acceso a los módulos de lambdas/agent y lambdas/pipeline
LAMBDAS_ROOT = Path(__file__).parent.parent / "lambdas"
if str(LAMBDAS_ROOT) not in sys.path:
    sys.path.insert(0, str(LAMBDAS_ROOT))


def pytest_addoption(parser):
    parser.addoption("--endpoint", action="store", default=None, help="URL de la API para tests E2E")
    parser.addoption("--live", action="store_true", default=False, help="Habilita tests que pegan a servicios live")


@pytest.fixture(scope="session")
def api_endpoint(request):
    """
    Obtiene el endpoint de la API:
    1. CLI arg (--endpoint)
    2. .env / variable de entorno (API_ENDPOINT)
    3. Auto-descubrimiento via 'terraform output -json' si se pasó --live
    """
    cli_val = request.config.getoption("--endpoint", default=None)
    if cli_val:
        return cli_val

    env_val = os.getenv("API_ENDPOINT")
    if env_val:
        return env_val

    tf_dir = Path(__file__).parent.parent / "terraform" / "main"
    res = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=tf_dir,
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        data = json.loads(res.stdout)
        if "query_endpoint" in data and "value" in data["query_endpoint"]:
            return data["query_endpoint"]["value"]

    raise ValueError(
        "No se pudo determinar el endpoint de la API para tests live. "
        "Configurá API_ENDPOINT en .env o pasá --endpoint https://.../query"
    )
