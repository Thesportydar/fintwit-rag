from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ENRICHMENT_VERSION = "v1"


class TweetEnrichment(BaseModel):
    tweet_id: str = Field(description="ID numérico o identificador del tweet")
    tickers: list[str] = Field(
        default_factory=list,
        description="Tickers o símbolos financieros identificados y normalizados en mayúsculas. Si no menciona activos específicos, lista vacía.",
    )
    sentiment: Literal["bullish", "bearish", "neutral", "unknown"] = Field(
        default="neutral",
        description="Sentimiento bursátil o financiero: 'bullish' (alcista/optimista), 'bearish' (bajista/pesimista/preocupación), 'neutral' (informativo/neutro).",
    )
    topics: list[str] = Field(
        default_factory=list,
        description="Tópicos de la conversación, eligiendo entre: 'acciones_locales', 'cedears_usa', 'deuda_soberana', 'deuda_corporativa', 'politica_monetaria_bcra', 'fx_dolar', 'inflacion_macro', 'cripto', 'commodities'.",
    )
    is_financial_insight: bool | None = Field(
        default=None,
        description="True o False cuando el clasificador pudo decidirlo; null si el tweet no fue clasificado.",
    )
    enrichment_status: Literal["classified", "unclassified"] = Field(
        default="classified",
        description="Indica si los metadatos fueron producidos por el clasificador o quedaron sin clasificar.",
    )
    enrichment_version: str = Field(
        default=ENRICHMENT_VERSION,
        description="Version del contrato de enriquecimiento.",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confianza global opcional del clasificador, entre 0 y 1.",
    )


class EnrichedTweetBatch(BaseModel):
    items: list[TweetEnrichment] = Field(
        default_factory=list,
        description="Lista de tweets enriquecidos correspondientes al lote procesado.",
    )
