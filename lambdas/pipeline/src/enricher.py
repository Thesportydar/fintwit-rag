from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI

from .config import PipelineConfig
from .models import ENRICHMENT_VERSION, EnrichedTweetBatch, TweetEnrichment

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ALLOWED_TOPICS = {
    "acciones_locales",
    "cedears_usa",
    "deuda_soberana",
    "deuda_corporativa",
    "politica_monetaria_bcra",
    "fx_dolar",
    "inflacion_macro",
    "cripto",
    "commodities",
}
_GEMINI_RESPONSE_SCHEMA = EnrichedTweetBatch.model_json_schema()


def _normalize_tickers(tickers: list[str]) -> list[str]:
    normalized: set[str] = set()
    for ticker in tickers:
        value = str(ticker).strip().lstrip("$").upper()
        if value and value.isascii() and value[0].isalpha() and value.isalnum() and 1 < len(value) <= 8:
            normalized.add(value)
        else:
            logger.warning("Se descarto ticker invalido del modelo: %s", ticker)
    return sorted(normalized)


def _normalize_topics(topics: list[str]) -> list[str]:
    normalized = {str(topic).strip().lower() for topic in topics}
    unknown = normalized - _ALLOWED_TOPICS
    if unknown:
        logger.warning("Se descartaron topics fuera del vocabulario: %s", sorted(unknown))
    return sorted(normalized & _ALLOWED_TOPICS)


def _unclassified_enrichment(tweet_id: str) -> TweetEnrichment:
    return TweetEnrichment(
        tweet_id=tweet_id,
        tickers=[],
        sentiment="unknown",
        topics=[],
        is_financial_insight=None,
        enrichment_status="unclassified",
        enrichment_version=ENRICHMENT_VERSION,
        confidence=None,
    )


def _format_batch(tweets: list[dict[str, Any]]) -> str:
    formatted_items = []
    for i, t in enumerate(tweets):
        t_id = str(t.get("tweet_id") or i)
        handle = t.get("user_handle") or "anon"
        content = t.get("content") or ""
        formatted_items.append(f"[ID: {t_id}] @{handle}: {content}")
    return "TWEETS A ANALIZAR:\n" + "\n\n".join(formatted_items)


def _normalize_results(parsed: EnrichedTweetBatch, tweets: list[dict[str, Any]]) -> dict[str, TweetEnrichment]:
    results = {}
    tweet_ids = {str(tweet.get("tweet_id") or "") for tweet in tweets}
    if parsed.items:
        for item in parsed.items:
            if item.tweet_id not in tweet_ids:
                logger.warning("El modelo devolvio un tweet_id fuera del lote: %s", item.tweet_id)
                continue
            results[item.tweet_id] = item.model_copy(
                update={
                    "tickers": _normalize_tickers(item.tickers),
                    "topics": _normalize_topics(item.topics),
                    "enrichment_version": ENRICHMENT_VERSION,
                }
            )

    for tweet in tweets:
        tweet_id = str(tweet.get("tweet_id") or "")
        if tweet_id and tweet_id not in results:
            results[tweet_id] = _unclassified_enrichment(tweet_id)
    return results


def _fallback_results(tweets: list[dict[str, Any]]) -> dict[str, TweetEnrichment]:
    return {
        tweet_id: _unclassified_enrichment(tweet_id)
        for tweet in tweets
        if (tweet_id := str(tweet.get("tweet_id") or ""))
    }


class TweetEnricher:
    def __init__(
        self,
        api_key: str,
        model: str | None = None,
    ):
        self.api_key = api_key
        self.model = model or os.getenv("ENRICHMENT_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=api_key)
        self.system_prompt = (_PROMPTS_DIR / "enrichment_prompt.txt").read_text(encoding="utf-8").strip()

    def enrich_batch(self, tweets: list[dict[str, Any]]) -> dict[str, TweetEnrichment]:
        """
        Enriquece un lote de tweets (10-20 tweets) usando LLM con Structured Outputs.
        Retorna un dict mapping {tweet_id: TweetEnrichment}.
        """
        if not tweets:
            return {}

        user_content = _format_batch(tweets)

        try:
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format=EnrichedTweetBatch,
            )
            parsed: EnrichedTweetBatch = completion.choices[0].message.parsed

            return _normalize_results(parsed, tweets)

        except Exception as exc:
            logger.warning(f"Error en enriquecimiento LLM batch: {exc}. Usando fallback por defecto.")
            return _fallback_results(tweets)


class GeminiTweetEnricher:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-lite",
        url: str = "https://generativelanguage.googleapis.com/v1beta/models",
        timeout: int = 90,
    ):
        if not api_key:
            raise ValueError("Falta GEMINI_API_KEY")
        self.api_key = api_key
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.system_prompt = (_PROMPTS_DIR / "enrichment_prompt.txt").read_text(encoding="utf-8").strip()

    def enrich_batch(self, tweets: list[dict[str, Any]]) -> dict[str, TweetEnrichment]:
        if not tweets:
            return {}

        request_body = {
            "system_instruction": {"parts": [{"text": self.system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": _format_batch(tweets)}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "responseJsonSchema": _GEMINI_RESPONSE_SCHEMA,
            },
        }
        try:
            response = requests.post(
                f"{self.url}/{self.model}:generateContent",
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json=request_body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            candidates = response.json().get("candidates", [])
            text = candidates[0]["content"]["parts"][0]["text"]
            parsed = EnrichedTweetBatch.model_validate(json.loads(text))
            return _normalize_results(parsed, tweets)
        except (KeyError, IndexError, TypeError, ValueError, requests.RequestException) as exc:
            logger.warning("Error en enriquecimiento Gemini batch: %s. Registros marcados como unclassified.", exc)
            return _fallback_results(tweets)


def create_tweet_enricher(
    config: PipelineConfig,
) -> TweetEnricher | GeminiTweetEnricher:
    if config.enrichment_provider == "gemini":
        return GeminiTweetEnricher(api_key=config.gemini_api_key, model=config.gemini_model)
    if config.enrichment_provider != "openai":
        raise ValueError(f"Proveedor de enrichment no soportado: {config.enrichment_provider}")
    return TweetEnricher(api_key=config.openai_api_key, model=config.enrichment_model)
