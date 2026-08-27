from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.synthesizer import Synthesizer
from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_EVAL_MODEL = os.getenv("EVAL_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")


class CustomDeepEvalLLM(DeepEvalBaseLLM):
    """Wrapper para usar modelos OpenAI en DeepEval."""

    def __init__(self, model: str | None = None):
        self.model_name = model or DEFAULT_EVAL_MODEL
        self.client = OpenAI()

    def load_model(self):
        return self.client

    def generate(self, prompt: str, schema: BaseModel = None):
        if schema:
            res = self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format=schema,
            )
            return res.choices[0].message.parsed
        else:
            res = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
            )
            return res.choices[0].message.content

    async def a_generate(self, prompt: str, schema: BaseModel = None):
        return self.generate(prompt, schema)

    def get_model_name(self):
        return self.model_name


SAMPLE_SEED_CONTEXTS = [
    [
        "La gallega (GGAL) presentó ganancias récord por $120.000M en el 1Q, impulsada por mayor margen de intermediación financiera.",
        "A pesar del balance de GGAL, ojo con la mora crediticia en el sector bancario que viene subiendo levemente.",
    ],
    [
        "Muy firme el tramo corto de la deuda soberana. El AL30 cerró en USD 58.50 y el GD30 en USD 61.20 con volumen sostenido.",
    ],
    [
        "El BCRA compró hoy USD 85M en el mercado oficial. La tasa de política monetaria se mantiene en 40% TNA.",
    ],
    [
        "El CCL cerró en $1280 mientras Bitcoin (BTC) superó los USD 65.000 con fuerte arbitraje local.",
    ],
]


def generate_with_deepeval_synthesizer(
    contexts: list[list[str]] | None = None,
    output_file: Path = DATA_DIR / "golden_eval_dataset.json",
    model: str | None = None,
    max_goldens_per_context: int = 1,
) -> list[dict[str, Any]]:
    """
    Genera dataset sintético usando el Synthesizer NATIVO de DeepEval.
    Aplica técnicas de evolución de prompts (reasoning, multicontext, hypothetical)
    para generar casos de prueba diversos.
    """
    selected_model = model or DEFAULT_EVAL_MODEL
    input_contexts = contexts or SAMPLE_SEED_CONTEXTS
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

    llm_wrapper = CustomDeepEvalLLM(model=selected_model)
    synthesizer = Synthesizer(model=llm_wrapper, async_mode=False)

    print(f"[GEN] Ejecutando Synthesizer nativo de DeepEval ({selected_model})...")
    goldens = synthesizer.generate_goldens_from_contexts(
        contexts=input_contexts,
        include_expected_output=True,
        max_goldens_per_context=max_goldens_per_context,
    )

    output_data = []
    for g in goldens:
        output_data.append(
            {
                "query": g.input,
                "expected_output": g.expected_output,
                "retrieval_context": g.context or [],
            }
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"[OK] Generados {len(output_data)} Goldens con DeepEval Synthesizer en {output_file}")
    return output_data


if __name__ == "__main__":
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    print("[RUN] Generando dataset sintético con DeepEval Synthesizer...")
    data = generate_with_deepeval_synthesizer()
    print("Preview del primer Golden generado:")
    print(json.dumps(data[0], indent=2, ensure_ascii=False))
