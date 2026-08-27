from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TweetEnrichment(BaseModel):
    tweet_id: str = Field(description="ID numérico o identificador del tweet")
    tickers: list[str] = Field(
        default_factory=list,
        description="Tickers financieros identificados y normalizados en mayúsculas (ej: ['GGAL', 'AL30', 'BTC', 'YPFD', 'SPY', 'USD']). Si no menciona activos específicos, lista vacía.",
    )
    sentiment: Literal["bullish", "bearish", "neutral"] = Field(
        default="neutral",
        description="Sentimiento bursátil o financiero: 'bullish' (alcista/optimista), 'bearish' (bajista/pesimista/preocupación), 'neutral' (informativo/neutro).",
    )
    topics: list[str] = Field(
        default_factory=list,
        description="Tópicos de la conversación, eligiendo entre: 'acciones_locales', 'cedears_usa', 'deuda_soberana', 'deuda_corporativa', 'politica_monetaria_bcra', 'fx_dolar', 'inflacion_macro', 'cripto', 'commodities'.",
    )
    is_financial_insight: bool = Field(
        default=True,
        description="True si el tweet contiene análisis, opinión, dato o comentario financiero/económico útil. False si es mero saludo, meme sin análisis, chiste o spam.",
    )


class EnrichedTweetBatch(BaseModel):
    items: list[TweetEnrichment] = Field(
        default_factory=list,
        description="Lista de tweets enriquecidos correspondientes al lote procesado.",
    )
