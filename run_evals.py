#!/usr/bin/env python3
"""
CLI Runner de Evaluaciones FinTwit RAG
======================================
Ejecuta la suite de evaluación en 3 capas usando DeepEval y Pytest.

Uso:
    python run_evals.py --layer 1       # Ingesta & Enriquecimiento Semántico
    python run_evals.py --layer 2       # Retrieval & Grafo CRAG
    python run_evals.py --layer 3       # Generación & Agente
    python run_evals.py --layer all     # Suite completa de evaluación
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Cargar .env si existe
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run_evaluation(layer: str):
    print("=" * 70)
    print(f"[RUN] INICIANDO EVALUACIONES FINTWIT RAG (Capa: {layer.upper()})")
    print("=" * 70)

    target_files = []
    if layer in ("1", "all"):
        target_files.append("evals/test_1_ingestion.py")
    if layer in ("2", "all"):
        target_files.append("evals/test_2_retrieval_crag.py")
    if layer in ("3", "all"):
        target_files.append("evals/test_3_generation_agent.py")

    cmd = [sys.executable, "-m", "pytest", "-s", "-v"] + target_files

    print(f"Ejecutando: {' '.join(cmd)}\n")
    exit_code = subprocess.call(cmd)

    print("\n" + "=" * 70)
    if exit_code == 0:
        print("[OK] TODAS LAS EVALUACIONES PASARON EXITOSAMENTE")
    else:
        print(f"[FAIL] ALGUNAS EVALUACIONES FALLARON (Código de salida: {exit_code})")
    print("=" * 70)

    sys.exit(exit_code)


def main():
    parser = argparse.ArgumentParser(description="Ejecutar suite de evaluación en 3 capas de FinTwit RAG")
    parser.add_argument(
        "--layer",
        choices=["1", "2", "3", "all"],
        default="all",
        help="Capa a evaluar (1: Ingesta, 2: Retrieval/CRAG, 3: Generación/Agente, all: Todas)",
    )
    args = parser.parse_args()
    run_evaluation(args.layer)


if __name__ == "__main__":
    main()
