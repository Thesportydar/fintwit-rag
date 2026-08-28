# AGENTS.md - FinTwit RAG Agent

Guia de contexto tecnico para agentes de IA trabajando en este repositorio.
Lee esto antes de tocar cualquier codigo.

---

## 1. Que es este proyecto

**FinTwit RAG** es un agente conversacional financiero impulsado por **LangGraph** y **AWS Bedrock AgentCore Runtime** bajo el protocolo **AG-UI (Agent User Interaction Protocol)**.
Analiza la conversacion financiera de Argentina y Wall Street en X (Twitter), recuperando tweets mediante busqueda hibrida (Dense + BM25 server-side inference en Qdrant + Jina Reranker), ejecutando un loop de correccion activa **CRAG (Corrective RAG)** y transmitiendo eventos Server-Sent Events (SSE) en tiempo real.

### Arquitectura General:
```
[ Frontend: assistant-ui / React ]
               | (POST /invocations con Bearer JWT / SSE Stream)
               v
[ Amazon Bedrock AgentCore Runtime ] (Docker ARM64 / FastAPI AG-UI en puerto 8080)
               |
   +-----------+----------------------------------------+
   v                                                    v
[ LangGraph StateGraph (CRAG Loop) ]            [ Persistencia DynamoDB ]
   +- maybe_summarize (Token window compression)   +- Checkpointer (hilos)
   +- agent_node (Decision de busqueda / ToolNode) +- Store (memoria semantica)
   +- tools: search_tweets
   |    +- Jina Embeddings (v5 text-nano)
   |    +- Qdrant Hybrid Search (Dense + BM25 + RRF)
   |    +- Jina Reranker (v3 top-N)
   +- check_relevance (Evaluador estructurado de relevancia)
   +- rewrite_query (Reescritura correctiva si score < 5.0)
   +- synthesize (Sintesis financiera analitica final)
```

---

## 2. Estructura del Repositorio

```
lambdas/
  agent/                 # Bedrock AgentCore Runtime (Docker ARM64 + FastAPI AG-UI)
    src/
      agent.py           # Instanciacion de servicios y compilacion del grafo
      config.py          # AppConfig (Single Source of Truth para variables de entorno)
      embeddings.py      # Clientes Jina Embeddings y Jina Rerank Compressor
      entrypoint.py      # Servidor ASGI FastAPI con endpoints /ping y /invocations (AG-UI)
      llm.py             # Fabrica unificada de LLM (OpenAI / Bedrock Converse)
      vector_store.py    # Filtros y Tool de busqueda hibrida en Qdrant
      prompts/           # Prompts del sistema (agent, synthesize, summarize, etc.)
      workflows/
        crag.py          # Definicion y nodos del grafo LangGraph con loop CRAG
    Dockerfile           # Imagen Linux/arm64 basada en python:3.13-slim-bookworm
    requirements.txt     # Dependencias de Python del agente
  pipeline/              # Pipeline de ingesta asincrono
    src/                 # Procesador de JSON crudo a Parquet y upsert en Qdrant
scripts/
  build_and_push_agent.sh # Script automatizado de login en ECR, buildx ARM64 y push
terraform/
  persistent/            # Infraestructura base (Hosting S3 + CloudFront SPA, ACM, Route53, EBS)
  main/                  # Infraestructura mutable (Bedrock AgentCore, ECR, IAM, Lambda, Qdrant EC2)
tests/
  unit/                  # Tests unitarios rapidos (test_crag.py, test_pipeline.py, etc.)
  e2e/                   # Tests en vivo contra AWS (test_agentcore_live.py con flag --live)
evals/                   # Evaluacion de RAG con DeepEval / G-Eval
```

---

## 3. Reglas de Desarrollo y Buenas Practicas

1. **Happy Path legible:** El codigo debe leerse de forma lineal y clara.
2. **Fail-Fast vs Fallbacks Silenciosos:**
   - **No silenciar errores criticos** con bloques `try...except` anidados que capturen todo o usen fallbacks que oculten el problema real.
   - Si una variable de entorno o servicio requerido falta, fallar de inmediato en el inicio (`from_env` / startup).
   - Si un fallback es legitimo para mantener la disponibilidad del servicio (ej: evaluacion CRAG o batch LLM en ingesta), **siempre loggear un warning explicito** (`logger.warning(...)`) para garantizar observabilidad.
3. **Single Source of Truth en Configuracion:**
   - Toda variable de entorno debe estar tipada y documentada en `AppConfig` (`lambdas/agent/src/config.py`).
   - Los submodulos no deben llamar a `os.environ` directamente si los valores pueden pasarse desde la configuracion.
4. **Infraestructura con Terraform:**
   - Nunca crear o modificar recursos de AWS a mano en la consola.
   - Los cambios de infraestructura se declaran en `terraform/main/` o `terraform/persistent/` y se aplican con `terraform apply -var-file=dev.tfvars`.
5. **AWS Profile:**
   - Para ejecuciones de CLI / Scripts / Tests en vivo: usar `AWS_PROFILE=dev-admin` (cuenta `563147762970`, region `us-east-1`).

---

## 4. Comandos Frecuentes

### Tests Unitarios
```bash
pytest tests/unit/ -v
```

### Tests E2E en Vivo contra AWS
```bash
AWS_PROFILE=dev-admin pytest tests/e2e/test_agentcore_live.py --live -v
```

### Build y Push del Contenedor ARM64 a ECR
```bash
./scripts/build_and_push_agent.sh dev-admin
```

### Despliegue de Infraestructura (Terraform)
```bash
cd terraform/main
terraform plan -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars
```

### Pre-commit Hooks
```bash
git add -A
pre-commit run
```

---

## 5. Que NO hacer

- [NO] **No usar hacks de `sys.path`:** El contenedor corre con `PYTHONPATH="/app"`. Usar siempre imports relativos o absolutos limpios (`from .agent import create_agent_app` o `from src.agent import ...`).
- [NO] **No modificar `.zip` de Lambdas a mano:** Son artefactos generados por Terraform / CI.
- [NO] **No commitear secrets ni API keys:** Todo secret vive en variables de entorno / SSM Parameter Store / Terraform tfvars ignorados por git.
- [NO] **No mezclar la logica de transporte con la logica del grafo:** `entrypoint.py` solo maneja FastAPI/AG-UI, `agent.py` conecta servicios y `crag.py` ejecuta el grafo puro.
