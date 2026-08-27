FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app"

WORKDIR /app

# Instalar dependencias del sistema minimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar requirements de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el codigo fuente y prompts
COPY src/ /app/src/

# Exponer puertos estandar
EXPOSE 8080 8000

# Entrypoint para Bedrock AgentCore Runtime
ENTRYPOINT ["python", "/app/src/entrypoint.py"]
