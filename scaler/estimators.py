import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Iterable
import requests

# Work units are seconds of expected single-worker service time.
BASE_SECONDS = {
    "route": 0.35,
    "lookup": 0.90,
    "transform": 2.80,
    "doc": 7.50,
}
SIZE_SLOPES = {
    "route": 0.0008,
    "lookup": 0.0010,
    "transform": 0.0015,
    "doc": 0.0020,
}


def _parse_message(raw: bytes | str) -> dict:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def metadata_cost(message: dict) -> float:
    kind = str(message.get("kind", "lookup")).lower()
    size_kb = float(message.get("size_kb", 0.0))
    base = BASE_SECONDS.get(kind, 1.50)
    slope = SIZE_SLOPES.get(kind, 0.0012)
    return max(0.10, base + slope * max(size_kb, 0.0))


class MetadataEstimator:
    name = "metadata"

    def estimate(self, raw_messages: Iterable[bytes | str]) -> list[float]:
        return [metadata_cost(_parse_message(m)) for m in raw_messages]


@dataclass
class CacheEntry:
    expires_at: float
    values: list[float]


class OpenAICompatibleEstimator:
    """
    Optional semantic estimator using any chat-completions-compatible endpoint.

    Required environment variables:
      LLM_ENDPOINT       Full HTTP endpoint. The caller controls provider/API version.
      LLM_API_KEY        Optional bearer or api-key value.
      LLM_MODEL          Model/deployment name if the endpoint requires a model field.
      LLM_AUTH_HEADER    Authorization header name. Default: Authorization.
      LLM_AUTH_PREFIX    Prefix for the key. Default: "Bearer ". Set to empty for api-key.

    The scaler sends only compact synthetic metadata from the test workload. Do not point
    this prototype at queues containing confidential payloads without a separate privacy review.
    """
    name = "llm"

    def __init__(self, timeout_s: float = 2.0, cache_ttl_s: float = 10.0):
        self.endpoint = os.getenv("LLM_ENDPOINT", "").strip()
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.model = os.getenv("LLM_MODEL", "").strip()
        self.auth_header = os.getenv("LLM_AUTH_HEADER", "Authorization")
        self.auth_prefix = os.getenv("LLM_AUTH_PREFIX", "Bearer ")
        self.timeout_s = timeout_s
        self.cache_ttl_s = cache_ttl_s
        self._cache: dict[str, CacheEntry] = {}
        self._fallback = MetadataEstimator()

    def _key(self, compact: list[dict]) -> str:
        body = json.dumps(compact, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()

    def estimate(self, raw_messages: Iterable[bytes | str]) -> list[float]:
        messages = [_parse_message(m) for m in raw_messages]
        if not messages:
            return []
        if not self.endpoint:
            return self._fallback.estimate([json.dumps(m) for m in messages])

        compact = [
            {
                "kind": m.get("kind"),
                "size_kb": round(float(m.get("size_kb", 0)), 2),
                "priority": m.get("priority", "normal"),
            }
            for m in messages
        ]
        key = self._key(compact)
        cached = self._cache.get(key)
        now = time.time()
        if cached and cached.expires_at > now:
            return cached.values

        prompt = (
            "Estimate single-worker service cost in seconds for each queued synthetic job. "
            "Return JSON only as {\"cost_seconds\":[number,...]}. Preserve input order. "
            "Use kind, size_kb, and priority. Keep every estimate between 0.1 and 30.0."
        )
        payload = {
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(compact, separators=(",", ":"))},
            ],
            "temperature": 0,
            "max_tokens": max(80, 12 * len(compact)),
        }
        if self.model:
            payload["model"] = self.model

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers[self.auth_header] = f"{self.auth_prefix}{self.api_key}"

        try:
            response = requests.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout_s)
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            parsed = json.loads(text)
            values = [min(30.0, max(0.1, float(x))) for x in parsed["cost_seconds"]]
            if len(values) != len(messages):
                raise ValueError("LLM returned the wrong number of cost estimates")
            self._cache[key] = CacheEntry(now + self.cache_ttl_s, values)
            return values
        except Exception:
            # Fail safe for a scaling control loop. The queue-count trigger remains the floor,
            # and the external scaler falls back to deterministic metadata estimation.
            return self._fallback.estimate([json.dumps(m) for m in messages])


def build_estimator(name: str):
    name = (name or "metadata").lower()
    if name == "llm":
        return OpenAICompatibleEstimator()
    return MetadataEstimator()
