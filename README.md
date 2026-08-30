# FinTwit RAG: Autonomous Financial Search & Agentic Intelligence

![Python](https://img.shields.io/badge/Python-3.13-blue.svg) ![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC.svg) ![AWS Bedrock](https://img.shields.io/badge/AWS-Bedrock_AgentCore-FF9900.svg) ![LangGraph](https://img.shields.io/badge/LangGraph-CRAG_Workflow-339933.svg) ![Qdrant](https://img.shields.io/badge/Qdrant-Hybrid_Search-E34F26.svg) ![OpenAI](https://img.shields.io/badge/OpenAI-LLM-412991.svg)

**FinTwit RAG** is a production-grade, stateful conversational financial agent powered by **LangGraph** and **Amazon Bedrock AgentCore Runtime** implementing the **AG-UI (Agent User Interaction)** protocol.

It autonomously investigates and synthesizes the Argentine and Wall Street financial conversation on X (Twitter), combining hybrid search (Dense + BM25 with Reciprocal Rank Fusion), contextual neural reranking, a **Corrective RAG (CRAG)** active evaluation loop, and real-time Server-Sent Events (SSE) streaming with enterprise safety hardening and cost caps.

---

## 1. System Architecture

```
[ Frontend: React 19 / Vite / assistant-ui ]
                    |  (POST /invocations con Bearer JWT / SSE Stream)
                    v
[ Amazon Bedrock AgentCore Runtime ] (Docker ARM64 / FastAPI AG-UI en puerto 8080)
                    |
      +-------------+------------------------------------+
      v                                                  v
[ LangGraph StateGraph (CRAG Loop) ]            [ Persistencia DynamoDB ]
   +- maybe_summarize (Token window compression)   +- Checkpointer (fintwit-checkpoints)
   +- agent_node (Planificación / Tool Calling)   +- Store (fintwit-store)
   +- tools: search_tweets                         +- Rate Limiter (fintwit-rate-limits)
   |    +- Jina Embeddings (v5 text-nano)
   |    +- Qdrant Hybrid Search (Dense + BM25 + RRF)
   |    +- Jina Reranker (v3 top-N)
   +- check_relevance (Evaluador estructurado)
   +- rewrite_query (Reescritura si score < 5.0)
   +- synthesize (Sintesis analitica con XML isolation)
```

---

## 2. Key Features & AI Engineering

### Corrective RAG (CRAG) Workflow
- **Hybrid Retrieval:** Blends semantic dense embeddings (`jina-embeddings-v5-text-nano`) and lexical server-side BM25 inference within [Qdrant](https://qdrant.tech/), fused via **Reciprocal Rank Fusion (RRF)**.
- **Neural Reranker:** Top candidates are re-evaluated and compressed using `jina-reranker-v3` before feeding context to the model.
- **Active Evaluation Loop:** If the structured relevance evaluator grades retrieved tweets below threshold (< 5.0/10), the agent enters a corrective branch, rewrites the query with search query reformulation techniques, and re-executes retrieval.
- **Stateful Memory & Context Compression:** Long-running conversations are persisted in **Amazon DynamoDB** (`DynamoDBSaver`). A dynamic token window compressor (`maybe_summarize`) condenses earlier turns into a running summary while preserving system instructions.

### Streaming Transport: Bedrock AgentCore Runtime + AG-UI
- Fully containerized (`python:3.13-slim-bookworm` ARM64) deployed on **Amazon Bedrock AgentCore Runtime**.
- Implements the standard **AG-UI protocol** over Server-Sent Events (SSE), streaming incremental token deltas, tool call lifecycle events, and structured error notifications.

---

## 3. Production Safety, Abuse Hardening & Boundaries

Designed from the ground up for safe public internet deployment:

1. **Strict Input Clamping:** User prompts are capped at **1,000 characters** in both UI and FastAPI middleware (`HTTP 400 Bad Request` rejection).
2. **Conversation Turn Limits:** Threads are limited to **20 user turns** max to prevent token inflation, infinite loops, and database bloat.
3. **Execution Timeout:** Streaming responses are guarded by an `asyncio.timeout(45s)` boundary, cleanly emitting structured `RUN_ERROR (TIMEOUT)` events to prevent runaway billing.
4. **Prompt Injection & Indirect Injection Defenses:**
   - **Tweet Isolation:** Retrieved social media content is encapsulated in strict XML tags (`<tweet author="@handle" date="YYYY-MM-DD">...</tweet>`) with breakout sanitization (`&lt;tweet`).
   - **Untrusted Context Directives:** System instructions command the LLM to treat tweet contents strictly as untrusted third-party quotes and ignore embedded user commands or URLs.
   - **Anti-Jailbreak Boundaries:** Explicit system prompts prevent internal system prompt leakage or policy overrides.
5. **Financial Advisory Boundaries:** Clear prohibition against direct investment advice ("comprá", "vendé") or price target guarantees, accompanied by mandatory disclaimers.
6. **Strict CORS:** Enforces whitelist validation limited to the production domain and authorized local development origins.

---

## 4. Cost Caps & Cloud Infrastructure (Terraform)

The infrastructure is 100% codified in **Terraform** split across persistent foundation resources and mutable application compute:

- **CloudFront Flat-Rate Plan ($0/month Free Tier):**
  - Production SPA (`rag.fintwit.com.ar`) hosted on private S3 through CloudFront with Origin Access Control (OAC).
  - Enrolled in the **CloudFront Flat-Rate Plan**, providing a **hard cost ceiling ($0/month)**, **bundled AWS WAF managed rules** at zero additional cost, and automatic AWS Shield DDoS mitigation.
- **AWS Monthly Cost Budget & Multi-Stage Alerts:**
  - Automated AWS Cost Budget ($25 USD/month) managed in Terraform (`budget.tf`).
  - Sends immediate email alerts at **80% actual cost**, **100% actual cost**, and **100% forecasted cost** (predictive alert before month-end).
- **Distributed DynamoDB Rate Limiting:**
  - Sliding-window rate limiter preventing API abuse on demo users.
  - Dedicated **Amazon Cognito** user pool with an `admin` group providing unlimited bypass for authorized administrators.
- **Decoupled Vector DB (EC2 + Persistent EBS):**
  - Qdrant index resides on a dedicated, persistent EBS volume (`terraform/persistent/`).
  - The EC2 compute instance (`terraform/main/`) can be destroyed and recreated on demand without losing any ingested tweet vectors.

---

## 5. Repository Structure

```
lambdas/
  agent/                 # Bedrock AgentCore Runtime (Docker ARM64 + FastAPI AG-UI)
    src/
      agent.py           # Servicio y compilador de grafo LangGraph
      config.py          # AppConfig (Single Source of Truth para env vars)
      embeddings.py      # Clientes Jina Embeddings y Jina Reranker
      entrypoint.py      # FastAPI ASGI con /ping, /invocations y SSE streaming
      llm.py             # Fabrica unificada de LLM (OpenAI / Bedrock Converse)
      vector_store.py    # Busqueda hibrida en Qdrant y aislamiento XML
      prompts/           # Prompts de sistema con defensas de inyeccion y finanzas
      workflows/
        crag.py          # Definicion del grafo LangGraph con loop CRAG
    Dockerfile           # Imagen ARM64 optimizada python:3.13-slim
    requirements.txt     # Dependencias del agente
  pipeline/              # Pipeline asincrono de ingesta de tweets
ui/                      # Frontend React 19 / Vite con Assistant UI y protocolo AG-UI
terraform/
  persistent/            # Infraestructura perenne (S3, CloudFront Flat-Rate, DynamoDB, ACM)
  main/                  # Infraestructura mutable (Bedrock AgentCore, Cognito, Qdrant EC2, Budget)
scripts/
  build_and_push_agent.sh # Script automatizado de buildx ARM64 y push a Amazon ECR
tests/
  unit/                  # Tests unitarios rapidos (CRAG, rate limits, safety clamps)
  e2e/                   # Tests en vivo contra AWS (Bedrock AgentCore con --live)
evals/                   # Evaluacion continua RAG con DeepEval
```

---

## 6. Development & Deployment Guide

### Prerequisites
- AWS CLI configured with `AWS_PROFILE=dev-admin` (Account `563147762970`, Region `us-east-1`).
- Docker with buildx support (for ARM64 cross-compilation).
- Terraform >= 1.5.0.

### 1. Provision Infrastructure
```bash
# Foundation layer (S3, CloudFront, DynamoDB, ACM)
cd terraform/persistent
terraform init && terraform apply -var-file="dev.tfvars"

# Application layer (Bedrock AgentCore, Cognito, Qdrant EC2, Budget)
cd ../main
terraform init && terraform apply -var-file="dev.tfvars"
```

### 2. Build and Deploy Agent Container
```bash
./scripts/build_and_push_agent.sh dev-admin
```

### 3. Run Automated Tests
```bash
# Unit test suite (CRAG workflow, safety middleware, rate limiting)
pytest tests/unit/ -v

# Live E2E test against AWS Bedrock AgentCore Runtime
AWS_PROFILE=dev-admin pytest tests/e2e/test_agentcore_live.py --live -v
```
