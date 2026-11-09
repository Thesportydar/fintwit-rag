# FinTwit RAG: Autonomous Financial Search & Agentic Intelligence

![CI](https://github.com/thesportydar/fintwit-rag/actions/workflows/ci.yml/badge.svg) ![Python](https://img.shields.io/badge/Python-3.13-blue.svg) ![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC.svg) ![AWS Bedrock](https://img.shields.io/badge/AWS-Bedrock_AgentCore-FF9900.svg) ![LangGraph](https://img.shields.io/badge/LangGraph-CRAG_Workflow-339933.svg) ![Qdrant](https://img.shields.io/badge/Qdrant-Hybrid_Search-E34F26.svg) ![OpenAI](https://img.shields.io/badge/OpenAI-LLM-412991.svg)

**FinTwit RAG** is a stateful conversational research assistant powered by **LangGraph** and **Amazon Bedrock AgentCore Runtime** implementing the **AG-UI (Agent User Interaction)** protocol.

It explores how the Argentine financial community discussed assets and events in a dated corpus of public X (Twitter) posts. It combines hybrid search (Dense + BM25 with Reciprocal Rank Fusion), contextual neural reranking, a corrective retrieval retry, and real-time Server-Sent Events (SSE) streaming with production safety boundaries and cost caps.

> **Portfolio demo:** [rag.fintwit.com.ar](https://rag.fintwit.com.ar)
> The application is intentionally read-only and analytical: it retrieves opinions from an indexed corpus of public posts, does not execute trades, and does not replace a market-data terminal or professional advice.

## Product contract

The product is a conversational research assistant over historical public opinion, not a live market-data terminal, a price prediction system, or an investment adviser. Its current scope is the Argentine FinTwit corpus; references to Wall Street are not treated as supported coverage unless the indexed corpus and evaluation set explicitly include them.

The assistant should:

- retrieve posts relevant to assets, events, accounts, and time windows;
- distinguish what an author said from an interpretation or aggregate observation;
- surface disagreement, stale context, limited coverage, and missing evidence;
- abstain from unsupported factual claims and direct buy/sell recommendations.

The live synthesis path is a single standard LLM call over XML-isolated tweet evidence. Relevant claims should cite stable evidence IDs inline as `[evidence:ID]`, and the prompt requires explicit coverage and limitations rather than a second handwritten JSON response schema.

The evidence boundary is explicit: indexed posts are dated opinions and may be incomplete, duplicated, contradictory, or stale. Retrieval relevance does not establish that a claim is true.

Enrichment metadata is probabilistic and produced by the batch classifier. The pipeline only validates and normalizes the model output; it does not maintain a hardcoded instrument or alias catalog. Each record carries an enrichment status, version, and optional confidence; failed classification is represented as `unclassified`, not as a confident neutral or financial label. The production Gemini path uses one configured API key and model; offline backfills can add their own rotation adapter without changing the Lambda runtime.

The standard LangGraph agent decides whether to call `search_tweets` and formulates the retrieval query from the conversation. Client-provided filters are normalized and enforced on every search call. This keeps routing aligned with the product's primary use case without maintaining a duplicate ticker catalog or a second query-planning layer.

After the agent calls the tool, a document/date coverage gate sends strong results directly to synthesis, invokes the relevance grader only for ambiguous evidence, and reserves one rewrite for recoverable coverage failures such as no results or missing temporal coverage. Natural-language aliases and ticker interpretation are left to the model and retrieval rather than duplicated in a hardcoded catalog. After an optional retry, synthesis receives the conversational turns plus only the latest retrieval result. Earlier evidence is not silently mixed into the final answer, and duplicate documents are removed before reranking while preserving the first retrieval order.

The retrieval result also receives deterministic quality signals from `evidence_quality.py`: document count, unique authors, contradictory stances, freshest date, stale context, coverage, and explicit limitations. These signals do not prove factual correctness; they make missing or conflicting evidence visible to synthesis.

Production synthesis uses one standard LLM pathway. The XML evidence boundary and citation instructions remain part of the prompt; citation compliance is an observable output property, not a second structured synthesis call.

After synthesis, a lightweight citation audit extracts `[evidence:ID]` references and compares them with the IDs in the latest retrieved context. It records missing or invalid citations in graph state without rejecting or regenerating the answer. The current AG-UI response exposes the synthesized text and its inline citations, not the audit object as a separate user-facing field.

LangSmith traces model calls and graph execution. The persisted graph state contains only workflow data needed for retries, evidence quality, citation auditing, and the final response; it does not duplicate tracing data in DynamoDB.

Temporal analysis keeps `tweet_timestamp` separate from `crawl_timestamp`. The ingestion bootstrap also ensures a Qdrant `datetime` payload index on `metadata.tweet_timestamp`, which is required by the runtime's temporal range filters. Temporal filtering remains part of retrieval metadata; the runtime does not claim to perform event-study or stance-evolution analytics.

The architectural decisions and the boundary between implemented behavior, measured behavior, and open work are documented in [`docs/ai-architecture.md`](docs/ai-architecture.md).

## Why this project is interesting

This is an end-to-end AI systems project rather than a chat UI wrapped around an LLM. A question travels through a stateful LangGraph workflow, lets the agent formulate a search query, searches the corpus with two complementary signals, reranks the candidates, checks evidence quality, and retries with a rewritten query when the first pass is weak. The result is streamed to the browser through AG-UI while the thread, rate limits, and infrastructure remain managed services.

The most useful surfaces for reviewing the implementation are:

- `lambdas/agent/src/workflows/crag.py`: graph orchestration, memory compression, relevance evaluation, and corrective retry.
- `lambdas/agent/src/vector_store.py`: Qdrant hybrid retrieval, metadata filters, reranking, and tweet isolation.
- `lambdas/agent/src/entrypoint.py`: AG-UI/SSE transport, authentication boundaries, input limits, and timeout handling.
- `ui/src/components/`: React client, Cognito login, persisted threads, filter state, and tool/reasoning visibility.
- `terraform/`: reproducible AWS infrastructure, cost budget, WAF/CloudFront, DynamoDB persistence, and AgentCore runtime.

The indexed content should be treated as dated public opinion, not verified facts. Responses must distinguish retrieved claims from model interpretation, surface contradictory views, and include the financial disclaimer when the query involves assets or investment decisions.

## What is live in the demo

The public interface is a deliberately small surface over a larger retrieval system:

1. A visitor is authenticated with a Cognito demo user and receives a short-lived access token.
2. The browser sends the conversation to the AgentCore runtime using AG-UI over SSE.
3. The LangGraph agent decides whether retrieval is needed, formulates the search query, applies optional date/account filters, and calls `search_tweets`.
4. Dense embeddings and server-side BM25 results are fused with RRF; the best candidates are reranked with Jina.
5. A deterministic coverage gate avoids unnecessary grader calls; ambiguous evidence is graded, recoverable gaps can trigger one rewrite, and the graph produces one final synthesis.

The UI exposes the active filters, tool calls, reasoning events, saved local threads, and the final disclaimer so the behavior is inspectable rather than pretending the model is an opaque oracle.

## Local development

The backend unit suite does not require AWS, Qdrant, Jina, or OpenAI credentials:

```bash
pytest tests/unit -q
ruff check lambdas tests
```

To build the production frontend:

```bash
pnpm --dir ui install --frozen-lockfile
pnpm --dir ui run build
```

The live deployment additionally requires the ignored `terraform/main/prod.tfvars`
and the variables described in `ui/.env.example`. Secrets and local `.env`
files are intentionally excluded from version control.


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
   +- maybe_summarize (Conversational memory compression) +- Checkpointer (fintwit-checkpoints)
   +- agent_node (Tool Calling)                      +- Store (fintwit-store)
   +- tools: search_tweets                         +- Rate Limiter (fintwit-rate-limits)
   |    +- Jina Embeddings (v5 text-nano)
   |    +- Qdrant Hybrid Search (Dense + BM25 + RRF)
   |    +- Jina Reranker (v3 top-N)
   +- assess_coverage (Gate determinista)
   +- check_relevance (Evaluador sólo para evidencia ambigua)
   +- rewrite_query (Reescritura sólo para gaps recuperables)
   +- synthesize (Sintesis analitica con XML isolation)
```

---

## 2. Key Features & AI Engineering

### Corrective RAG (CRAG) Workflow
- **Hybrid Retrieval:** Blends semantic dense embeddings (`jina-embeddings-v5-text-nano`) and lexical server-side BM25 inference within [Qdrant](https://qdrant.tech/), fused via **Reciprocal Rank Fusion (RRF)**.
- **Neural Reranker:** Top candidates are re-evaluated and compressed using `jina-reranker-v3` before feeding context to the model.
- **Cost-bounded CRAG Loop:** The agent retrieves when the conversation calls for research. Deterministic coverage checks send strong results to synthesis, ambiguous results to the structured relevance evaluator, and only recoverable gaps to one corrective rewrite before the single final synthesis.
- **Stateful Memory & Context Compression:** Long-running conversations are persisted in **Amazon DynamoDB** (`DynamoDBSaver`). A dynamic token window compressor (`maybe_summarize`) condenses dialogue turns into a conversational summary while excluding retrieved tweets, tool calls, URLs, and retrieval metadata from that memory.

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
- **Managed Vector DB (Qdrant Cloud):**
  - The production corpus uses Qdrant Cloud with hybrid dense + BM25 retrieval.
  - The former self-hosted EC2, EBS, Elastic IP, security group, and Route 53 record have been retired.
  - The Qdrant snapshot identifier remains in the persistent layer as a recovery reference, but no compute resource is provisioned for it.

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
  main/                  # Infraestructura mutable (Bedrock AgentCore, Cognito, Budget, pipeline)
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
- AWS CLI configured with `AWS_PROFILE=prod-admin` (Account `188494185674`, Region `us-east-1`); Terraform runs with `prod-terraform-admin`.
- Docker with buildx support (for ARM64 cross-compilation).
- Terraform >= 1.5.0.

### 1. Bootstrap and manage infrastructure with Terraform
```bash
# Foundation layer (S3, CloudFront, DynamoDB, ACM)
cd terraform/persistent
export TF_DATA_DIR=.terraform-prod
terraform init -reconfigure -backend-config=backend.prod.conf -backend-config="key=prod/persistent/terraform.tfstate"
terraform apply -var-file="prod.tfvars"

# Application layer (Bedrock AgentCore, Cognito, Budget, pipeline)
cd ../main
export TF_DATA_DIR=.terraform-prod
terraform init -reconfigure -backend-config=backend.prod.conf -backend-config="key=prod/main/terraform.tfstate"
terraform apply -var-file="prod.tfvars"
```

Terraform owns durable resources and platform configuration: S3, CloudFront,
Route 53/ACM, DynamoDB, ECR, IAM, Cognito, AgentCore networking/authorization,
Lambda wiring, budgets, and event rules. This remains the local/bootstrap path
until a separate Terraform workflow is introduced. It must be able to rebuild
the platform from an empty account.

Terraform creates the initial AgentCore runtime from `agent_image_tag`. After
that, `agent_runtime_artifact` is intentionally ignored so a later Terraform
apply cannot roll back an image released by CI.

### 2. Release application artifacts with CI
```bash
ENV=prod ./scripts/build_and_push_agent.sh prod-admin <immutable-tag>
```

The AgentCore deployment follows the same GitHub OIDC pattern as the parent
`twitter-scraper` repository. Configure the pre-existing role through the
`AWS_ROLE_ARN` secret plus the
`AWS_REGION`, `AGENTCORE_ECR_REPOSITORY`, and `AGENTCORE_RUNTIME_ID`
repository variables. Pushes touching
`lambdas/agent/` then build an ARM64 image with an immutable commit tag,
publish it to ECR, and update the existing runtime while preserving its
configuration.

CI owns application releases: the AgentCore ARM64 image and runtime version,
the frontend static bundle (already deployed by `deploy-front.yml`), and,
in a later step, the ingestion Lambda package. CI runs tests before publishing
and uses the same OIDC role for AWS access; it does not run a full Terraform
apply as part of an application release.

The ingestion Lambda is currently still packaged and updated by Terraform
because its source and dependency layer are declared in `terraform/main`.
Moving it to CI requires an artifact bucket or Lambda-compatible package
release flow, followed by removing its source-code ownership from Terraform.

### 3. Run Automated Tests
```bash
# Unit test suite (CRAG workflow, safety middleware, rate limiting)
pytest tests/unit/ -v

# Live E2E test against AWS Bedrock AgentCore Runtime
AWS_PROFILE=prod-admin pytest tests/e2e/test_agentcore_live.py --live -v

# Terraform validation
terraform fmt -check -recursive terraform
terraform -chdir=terraform/main init -backend=false
terraform -chdir=terraform/main validate
terraform -chdir=terraform/persistent init -backend=false
terraform -chdir=terraform/persistent validate
```
