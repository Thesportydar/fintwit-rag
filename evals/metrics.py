from __future__ import annotations

import os

from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams

DEFAULT_EVAL_MODEL = os.getenv("EVAL_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def create_faithfulness_metric(
    model: str | None = None,
    threshold: float = 0.8,
) -> GEval:
    """
    Métrica G-Eval para evaluar Groundedness (ausencia de alucinaciones) frente al contexto recuperado.
    """
    return GEval(
        name="Faithfulness",
        criteria=(
            "Evaluar si todas las afirmaciones, cifras, nombres y conclusiones expresadas en actual_output "
            "están 100% fundamentadas y respaldadas por los fragmentos en retrieval_context. La respuesta no "
            "debe contener alucinaciones, datos no presentes en el contexto ni suposiciones inventadas."
        ),
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT,
        ],
        threshold=threshold,
        model=model or DEFAULT_EVAL_MODEL,
        async_mode=False,
    )


def create_fintwit_synthesis_metric(
    model: str | None = None,
    threshold: float = 0.7,
) -> GEval:
    """
    Métrica G-Eval para evaluar la calidad de síntesis de consenso de mercado en FinTwit.
    Verifica que la respuesta:
    1. Refleje adecuadamente el balance de opiniones (bullish vs bearish) presentes en los tweets.
    2. Mencione los instrumentos y métricas reales presentes en el contexto.
    3. No invente cotizaciones, precios objetivos ni proyecciones que no estén respaldadas por la evidencia.
    """
    return GEval(
        name="FinTwit Market Synthesis",
        criteria=(
            "Evaluar si la respuesta sintetiza de manera precisa, equilibrada y fiel el consenso de mercado "
            "y los datos contenidos en los tweets recuperados (retrieval_context). La respuesta debe capturar "
            "las diferentes perspectivas (alcistas/bajistas), atribuir adecuadamente el contexto y NO inventar "
            "datos financieros, tickers o balances no respaldados."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT,
        ],
        threshold=threshold,
        model=model or DEFAULT_EVAL_MODEL,
        async_mode=False,
    )


def create_contextual_relevancy_metric(
    model: str | None = None,
    threshold: float = 0.7,
) -> GEval:
    """
    Métrica G-Eval para evaluar la pertinencia del contexto recuperado frente a la consulta.
    """
    return GEval(
        name="Contextual Relevancy",
        criteria=(
            "Evaluar si los fragmentos textuales recuperados (retrieval_context) son directamente pertinentes, "
            "relevantes y útiles para responder de forma precisa a la consulta del usuario (input)."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT,
        ],
        threshold=threshold,
        model=model or DEFAULT_EVAL_MODEL,
        async_mode=False,
    )


def create_fintwit_answer_relevancy_metric(
    model: str | None = None,
    threshold: float = 0.7,
) -> GEval:
    """
    Métrica G-Eval adaptada a FinTwit para evaluar si la respuesta atiende directamente la consulta
    financiera del usuario (reconociendo activos como AL30, GD30, GGAL, LECAP, etc.).
    """
    return GEval(
        name="FinTwit Answer Relevancy",
        criteria=(
            "Evaluar si la respuesta (actual_output) responde de manera directa, relevante, concisa y precisa a la "
            "consulta del usuario (input), comprendiendo la terminología e instrumentos financieros locales "
            "(ej: bonos soberanos como AL30 y GD30, acciones locales, política monetaria, tipo de cambio)."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        threshold=threshold,
        model=model or DEFAULT_EVAL_MODEL,
        async_mode=False,
    )
