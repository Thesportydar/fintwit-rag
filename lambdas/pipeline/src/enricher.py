from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from .models import EnrichedTweetBatch, TweetEnrichment

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


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

        formatted_items = []
        for i, t in enumerate(tweets):
            t_id = str(t.get("tweet_id") or i)
            handle = t.get("user_handle") or "anon"
            content = t.get("content") or ""
            formatted_items.append(f"[ID: {t_id}] @{handle}: {content}")

        user_content = "TWEETS A ANALIZAR:\n" + "\n\n".join(formatted_items)

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

            results = {}
            if parsed and parsed.items:
                for item in parsed.items:
                    results[item.tweet_id] = item

            # Asegurar que todos los tweets del lote tengan un resultado
            for t in tweets:
                t_id = str(t.get("tweet_id") or "")
                if t_id and t_id not in results:
                    results[t_id] = TweetEnrichment(
                        tweet_id=t_id,
                        tickers=[],
                        sentiment="neutral",
                        topics=[],
                        is_financial_insight=True,
                    )

            return results

        except Exception as exc:
            logger.warning(f"Error en enriquecimiento LLM batch: {exc}. Usando fallback por defecto.")
            fallback = {}
            for t in tweets:
                t_id = str(t.get("tweet_id") or "")
                fallback[t_id] = TweetEnrichment(
                    tweet_id=t_id,
                    tickers=[],
                    sentiment="neutral",
                    topics=[],
                    is_financial_insight=True,
                )
            return fallback
