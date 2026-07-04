"""Provider interfaces for the LLM and the embedding model.

Two implementations are provided for each:

* ``OpenAI*`` : real network-backed implementations (require ``OPENAI_API_KEY``).
* ``Mock*``   : deterministic, offline implementations used for local dev,
  CI and the mock verification path. Mock embeddings are hash-based vectors,
  so the same text always maps to the same vector (stable retrieval).

The factory functions :func:`get_embedder` and :func:`get_llm` pick the right
implementation based on :class:`~chatbot.config.Config`.
"""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import List, Sequence

from .config import Config


# ---------------------------------------------------------------------------
# Abstract interfaces
# ---------------------------------------------------------------------------
class Embedder(ABC):
    """Turns text into fixed-length float vectors."""

    dim: int

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Embed a batch of texts."""

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


class LLM(ABC):
    """Generates a natural-language answer from a prompt + context."""

    @abstractmethod
    def generate(self, system: str, user: str) -> str:
        """Return a completion for the given system + user messages."""


# ---------------------------------------------------------------------------
# Mock implementations (offline, deterministic)
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Common English stopwords stripped before embedding so retrieval is driven by
# meaningful, distinctive tokens rather than filler words.
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have how i in is it its of on or that the
    this to was were what when where which who will with you your do does can could my
    me we our they them their he she his her but not no if then than so such about into
    over under out up down off just also very more most some any all each other""".split()
)


def _stem(token: str) -> str:
    """Very light suffix stripping so plurals/verb forms match (refund/refunds)."""
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _tokenize(text: str) -> List[str]:
    return [
        _stem(t)
        for t in _TOKEN_RE.findall(text.lower())
        if t not in _STOPWORDS and len(t) > 1
    ]


class MockEmbedder(Embedder):
    """Deterministic hashed bag-of-words embedder (offline, no network).

    Tokens (stopwords removed) plus adjacent-token bigrams are hashed into
    ``dim`` positive-weighted buckets and the vector is L2-normalised. Using
    positive weights + bigrams means cosine similarity closely tracks genuine
    token/phrase overlap, so questions retrieve the chunks that actually share
    their vocabulary -- good enough for meaningful RAG without any API calls.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _bucket(self, feature: str) -> int:
        h = hashlib.sha256(feature.encode("utf-8")).digest()
        return int.from_bytes(h[:4], "big") % self.dim

    def _features(self, text: str) -> List[str]:
        tokens = _tokenize(text)
        # Unigrams weighted alongside bigrams for a bit of phrase awareness.
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        return tokens + bigrams

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for feature in self._features(text):
                vec[self._bucket(feature)] += 1.0
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors


class MockLLM(LLM):
    """Deterministic extractive 'LLM'.

    It does not invent facts: it stitches together the provided context so the
    output is always grounded. This keeps the mock path honest -- an answer can
    only contain what retrieval supplied.
    """

    def generate(self, system: str, user: str) -> str:
        # The user prompt embeds the question and the retrieved context. We
        # extract the context block and summarise the most relevant sentence.
        question = _extract_block(user, "QUESTION:")
        context = _extract_block(user, "CONTEXT:")

        if not context.strip():
            return "I don't have enough information to answer that confidently."

        q_tokens = set(_tokenize(question))
        # Split context into sentences and rank by token overlap w/ question.
        sentences = re.split(r"(?<=[.!?])\s+", context.replace("\n", " "))
        scored = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            overlap = len(q_tokens & set(_tokenize(sent)))
            scored.append((overlap, sent))
        scored.sort(key=lambda x: x[0], reverse=True)

        best = [s for score, s in scored[:2] if score > 0]
        if not best:
            best = [scored[0][1]] if scored else []
        answer = " ".join(best)
        return f"Based on our documentation: {answer}"


def _extract_block(text: str, label: str) -> str:
    """Extract the text following ``label`` up to the next ALL-CAPS label."""
    idx = text.find(label)
    if idx == -1:
        return ""
    rest = text[idx + len(label):]
    # Stop at the next label like "CONTEXT:" or "QUESTION:".
    m = re.search(r"\n[A-Z]{3,}:", rest)
    if m:
        rest = rest[: m.start()]
    return rest.strip()


# ---------------------------------------------------------------------------
# OpenAI implementations (network-backed)
# ---------------------------------------------------------------------------
class OpenAIEmbedder(Embedder):
    def __init__(self, api_key: str, model: str, dim: int = 1536) -> None:
        from openai import OpenAI  # imported lazily so mock mode needs no dep

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        resp = self._client.embeddings.create(model=self._model, input=list(texts))
        return [d.embedding for d in resp.data]


class OpenAILLM(LLM):
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI  # lazy import

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""


class OpenRouterLLM(LLM):
    """Open-source chat models via OpenRouter's OpenAI-compatible API.

    OpenRouter serves top open-weight models (DeepSeek V4/R2, Llama 4, Qwen 3,
    GLM) through the OpenAI SDK — we just point the SDK at OpenRouter's
    ``base_url``. This is the recommended production LLM for 24/7 support: cheap,
    fast, and quality on par with GPT-4-class models. Embeddings are handled
    separately (see :func:`get_embedder`) since OpenRouter is chat-focused.
    """

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        from openai import OpenAI  # lazy import

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def generate(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            extra_headers={
                "HTTP-Referer": "https://github.com/500-ai-agents-projects",
                "X-Title": "Support Chatbot Agent",
            },
        )
        return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------
def get_embedder(config: Config) -> Embedder:
    if config.is_mock:
        return MockEmbedder(dim=config.embedding_dim)
    if config.llm_provider == "openrouter":
        # OpenRouter is chat-focused; use local hashed embeddings by default so
        # retrieval works with zero embedding-API cost. Opt into OpenAI
        # embeddings by setting EMBEDDING_BACKEND=openai (+ OPENAI_API_KEY).
        if config.embedding_backend == "openai":
            if not config.openai_api_key:
                raise RuntimeError(
                    "EMBEDDING_BACKEND=openai requires OPENAI_API_KEY. "
                    "Use EMBEDDING_BACKEND=local (default) for offline embeddings."
                )
            return OpenAIEmbedder(config.openai_api_key, config.openai_embedding_model)
        return MockEmbedder(dim=config.embedding_dim)
    if not config.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required when LLM_PROVIDER=openai. "
            "Set LLM_PROVIDER=mock to run offline."
        )
    return OpenAIEmbedder(config.openai_api_key, config.openai_embedding_model)


def get_llm(config: Config) -> LLM:
    if config.is_mock:
        return MockLLM()
    if config.llm_provider == "openrouter":
        if not config.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter. "
                "Get one at https://openrouter.ai/keys or set LLM_PROVIDER=mock."
            )
        return OpenRouterLLM(
            config.openrouter_api_key, config.openrouter_model, config.openrouter_base_url
        )
    if not config.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required when LLM_PROVIDER=openai. "
            "Set LLM_PROVIDER=mock to run offline."
        )
    return OpenAILLM(config.openai_api_key, config.openai_chat_model)
