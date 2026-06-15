# 🚀 FinTwit RAG: End-to-End Serverless AI Search

![Python](https://img.shields.io/badge/Python-3.13-blue.svg) ![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC.svg) ![AWS](https://img.shields.io/badge/AWS-Serverless-FF9900.svg) ![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-E34F26.svg) ![OpenAI](https://img.shields.io/badge/OpenAI-LLM-412991.svg)

An end-to-end **Agentic AI** system and **Retrieval-Augmented Generation (RAG)** pipeline, purpose-built to autonomously query, reason, and synthesize deep insights from the Argentine Financial Twitter community (FinTwit).

Built with modern **AI Engineering** principles, the architecture orchestrates autonomous **LangChain / LangGraph** reasoning agents, seamlessly integrated with a decoupled vector database (Qdrant) and a fully automated, serverless AWS cloud infrastructure.

## 🤖 Agentic Architecture & Memory

At the core of the system is a sophisticated, tool-calling **Agentic AI** engine powered by **LangChain** and **LangGraph**, orchestrating a resilient and stateful conversational workflow:
- **Persistent Memory:** Conversations are checkpointed to **Amazon DynamoDB** using `DynamoDBSaver`, enabling long-running threads that remember user context across sessions via `thread_id`.
- **Context Management:** Implemented a custom `SummarizationMiddleware` to prevent context window overflows. It dynamically tracks token usage and compresses historical messages into a running summary while preserving system prompts.
- **Resiliency:** Built-in `ModelRetryMiddleware` and `ToolRetryMiddleware` gracefully handle transient network failures, rate limits, and API timeouts.

## 🧠 AI & Retrieval Pipeline

- **Agentic Retrieval (Tool Calling):** The LLM operates as an autonomous agent, intelligently deciding when to trigger search tools, formulate queries, and synthesize the retrieved Fintwit metadata (dates, authors) rather than relying on naive semantic search.
- **Embeddings:** [Jina AI](https://jina.ai/) (`jina-embeddings-v5-text-nano`) for high-quality, dense vector representations.
- **Vector Storage:** [Qdrant](https://qdrant.tech/) running on a lightweight EC2 instance for blazing-fast similarity search.
- **Reranking:** `jina-reranker-v3` to refine search results contextually before generation.
- **Generation:** Advanced chat models (e.g. `gpt-5.4` / Claude) for synthesizing final answers based strictly on retrieved context.

## 🏗️ Cloud Architecture & IaC (Terraform)

The infrastructure is fully automated using **Terraform**, optimized for cost-efficiency without sacrificing data persistence.

1. **Serverless API (AWS Lambda + API Gateway):**
   - Handles incoming REST requests (non-streaming, decoupled from frontend).
   - Orchestrates the agentic `Retrieval` → `Reranking` → `LLM Generation` pipeline.
   - Integrates directly with DynamoDB for state persistence (Checkpointer).
   - Served securely over a custom HTTPS domain mapped via Route 53 & AWS Certificate Manager.

2. **Decoupled Vector Database (EC2 + EBS + SSM):**
   - **State Separation:** The Qdrant data is persisted on an independent EBS volume (`terraform/persistent/`), securely mapped via AWS Systems Manager (SSM) Parameter Store.
   - **Cost-Optimized Compute:** The EC2 compute layer (`terraform/main/`) can be destroyed and recreated on demand to save costs, automatically re-attaching the persisted vector indices on boot.

3. **Secure Compute Access:**
   - **No Open SSH:** The EC2 instance utilizes an AWS IAM Instance Profile with `AmazonSSMManagedInstanceCore` for secure, keyless terminal access via AWS Session Manager.

## 🎨 Frontend UI

The user interface (`/ui/`) is a modern React 19 / Vite Single Page Application. It is heavily inspired by the [Assistant UI Claude Example](https://github.com/langchain-ai/langgraphjs/tree/main/examples/assistant-ui-claude), customized with several key enhancements:
- **Stateless Agentic Runtime:** Engineered a custom `useExternalStoreRuntime` to orchestrate robust REST communication with the AWS Lambda backend, ensuring a highly decoupled and resilient client-agent architecture.
- **Dynamic Context Injection:** A custom interface allows users to inject precise metadata constraints (date boundaries, specific Twitter handles) dynamically into the agent's retrieval context.

## 📂 Repository Structure

- `/ui/`: React 19 frontend application with custom Assistant UI runtime.
- `/lambda/`: Python 3.13 source code (`src/`) and `pytest` suite for the serverless API.
- `/ec2/`: Bootstrapping scripts (`user_data.sh`) to safely mount the detached EBS volume and launch Qdrant via Docker.
- `/terraform/persistent/`: IaC for the lifecycle-independent EBS storage, S3 bucket, DynamoDB, and CloudFront.
- `/terraform/main/`: IaC for the ephemeral compute, API Gateway, networking, and serverless resources.

## 🚀 Deployment Guide

### Prerequisites
- AWS CLI (`aws configure`) & Terraform installed.
- Valid API Keys in your environment (Jina, OpenAI, Qdrant).
- Provide variables via `dev.tfvars` (see `dev.tfvars.example`).

### 1. Provision Persistent Data Layer
```bash
cd terraform/persistent
terraform init && terraform apply -var-file="dev.tfvars"
```

### 2. Provision Ephemeral Compute & API
```bash
cd ../main
terraform init && terraform apply -var-file="dev.tfvars"
```
*Outputs will display the Custom API Domain, Qdrant Dashboard URL, and EC2 Instance ID.*

### 3. Spin Down (Cost Saving)
```bash
cd terraform/main
terraform destroy -var-file="dev.tfvars"
```
*(The Vector DB EBS volume remains safe, allowing you to resume instantly next time).*

## 🚧 Security Hardening & Future Roadmap

While the current architecture is highly optimized for developer velocity and cost-efficiency, scaling to a zero-trust or strictly compliant environment would naturally introduce the following network isolation enhancements:
- **VPC & Private Subnets:** Move the Qdrant EC2 instance into a private subnet, restricting all direct inbound internet access.
- **ALB & TLS Termination:** Place an Application Load Balancer in front of Qdrant to handle SSL/TLS termination and secure internal traffic routing.
- **Lambda VPC Integration:** Attach the serverless API directly to the VPC to query Qdrant privately, utilizing a NAT Gateway for necessary outbound API requests (e.g., OpenAI, Jina).
