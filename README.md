# 🚀 FinTwit RAG: End-to-End Serverless AI Search

![Python](https://img.shields.io/badge/Python-3.13-blue.svg) ![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC.svg) ![AWS](https://img.shields.io/badge/AWS-Serverless-FF9900.svg) ![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-E34F26.svg) ![OpenAI](https://img.shields.io/badge/OpenAI-LLM-412991.svg)

An end-to-end **Retrieval-Augmented Generation (RAG)** pipeline and infrastructure designed to query and synthesize insights from the Argentine Financial Twitter community (FinTwit).

The backend integrates an embedding and retrieval pipeline with automated Cloud Infrastructure as Code (IaC), deploying a serverless API and a decoupled vector database on AWS.

## 🧠 AI & Retrieval Pipeline

- **Embeddings:** [Jina AI](https://jina.ai/) (`jina-embeddings-v5-text-nano`) for high-quality, dense vector representations.
- **Vector Storage:** [Qdrant](https://qdrant.tech/) running on a lightweight EC2 instance for blazing-fast similarity search.
- **Reranking:** `jina-reranker-v3` to refine search results contextually before generation.
- **Generation:** OpenAI (`gpt-5.4`) / Anthropic Claude for synthesizing final answers based strictly on retrieved context.

## 🏗️ Cloud Architecture & IaC (Terraform)

The infrastructure is fully automated using **Terraform**, optimized for cost-efficiency without sacrificing data persistence.

1. **Serverless API (AWS Lambda + API Gateway):**
   - Handles incoming natural language queries.
   - Orchestrates the `Embedding` → `Retrieval` → `Reranking` → `LLM Generation` pipeline.
   - Served securely over a custom HTTPS domain mapped via Route 53 & AWS Certificate Manager.

2. **Decoupled Vector Database (EC2 + EBS + SSM):**
   - **State Separation:** The Qdrant data is persisted on an independent EBS volume (`terraform/persistent/`), securely mapped via AWS Systems Manager (SSM) Parameter Store.
   - **Cost-Optimized Compute:** The EC2 compute layer (`terraform/main/`) can be destroyed and recreated on demand to save costs, automatically re-attaching the persisted vector indices on boot.

3. **Secure Compute Access:**
   - **No Open SSH:** The EC2 instance utilizes an AWS IAM Instance Profile with `AmazonSSMManagedInstanceCore` for secure, keyless terminal access via AWS Session Manager.

## 📂 Repository Structure

- `/lambda/`: Python 3.13 source code (`src/`) and `pytest` suite for the serverless API.
- `/ec2/`: Bootstrapping scripts (`user_data.sh`) to safely mount the detached EBS volume and launch Qdrant via Docker.
- `/terraform/persistent/`: IaC for the lifecycle-independent EBS storage.
- `/terraform/main/`: IaC for the ephemeral compute, networking, DNS, and serverless resources.

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

## 🚧 Enterprise Considerations & Next Steps

While this architecture is highly optimized for developer velocity and cost-efficiency, a true enterprise-grade deployment should implement the following network security enhancements:
- **Private Subnets & TLS:** The EC2 instance currently exposes the Qdrant HTTP port directly. For production, the vector database should be moved to a private subnet behind an Application Load Balancer (ALB) with TLS termination, or accessed privately by attaching the Lambda to the VPC (which would require a NAT Gateway for outbound Jina/OpenAI API requests).
