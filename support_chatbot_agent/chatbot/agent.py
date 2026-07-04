"""The RAG answer agent with an escalation / QA gate.

Flow:  question -> embed -> retrieve top-k -> confidence gate -> answer.

If the top retrieval similarity is below ``confidence_threshold`` we escalate to
a human instead of letting the model hallucinate. The agent always returns the
cited source chunks and a confidence score alongside the answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .config import Config
from .llm import LLM, Embedder, get_embedder, get_llm
from .vectorstore import SearchResult, VectorStore

SYSTEM_PROMPT = (
    "You are a helpful, concise customer-support assistant. "
    "Answer ONLY using the provided context. If the context does not contain "
    "the answer, say you are not sure and that a human will follow up. "
    "Never invent facts, prices, or policies."
)

ESCALATION_MESSAGE = (
    "I'm not fully confident I can answer that accurately, so I'm routing you to "
    "a human support agent who will follow up shortly."
)


@dataclass
class Source:
    """A cited knowledge-base chunk supporting the answer."""

    id: str
    source: str
    score: float
    snippet: str


@dataclass
class AnswerResult:
    """The full result returned by the agent for one question."""

    question: str
    answer: str
    confidence: float
    escalate: bool
    sources: List[Source] = field(default_factory=list)
    tokens_used: int = 0

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "confidence": round(self.confidence, 4),
            "escalate": self.escalate,
            "sources": [s.__dict__ for s in self.sources],
            "tokens_used": self.tokens_used,
        }


def estimate_tokens(*texts: str) -> int:
    """Rough token estimate (~4 chars/token) good enough for billing."""
    total_chars = sum(len(t) for t in texts)
    return max(1, total_chars // 4)


def _build_context(results: List[SearchResult]) -> str:
    blocks = []
    for i, r in enumerate(results, start=1):
        blocks.append(f"[Source {i} | {r.chunk.source}]\n{r.chunk.text}")
    return "\n\n".join(blocks)


class SupportAgent:
    """Retrieval-augmented support agent."""

    def __init__(
        self,
        config: Config,
        store: VectorStore,
        embedder: Embedder | None = None,
        llm: LLM | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.embedder = embedder or get_embedder(config)
        self.llm = llm or get_llm(config)

    def answer(self, question: str) -> AnswerResult:
        question = (question or "").strip()
        if not question:
            return AnswerResult(
                question=question,
                answer="Please ask a question.",
                confidence=0.0,
                escalate=True,
                sources=[],
                tokens_used=0,
            )

        query_emb = self.embedder.embed_one(question)
        results = self.store.search(query_emb, top_k=self.config.top_k)

        confidence = results[0].score if results else 0.0
        sources = [
            Source(
                id=r.chunk.id,
                source=r.chunk.source,
                score=round(r.score, 4),
                snippet=r.chunk.text[:240].strip(),
            )
            for r in results
        ]

        # --- QA / escalation gate ---------------------------------------
        if confidence < self.config.confidence_threshold or not results:
            return AnswerResult(
                question=question,
                answer=ESCALATION_MESSAGE,
                confidence=confidence,
                escalate=True,
                sources=sources,
                tokens_used=estimate_tokens(question),
            )

        context = _build_context(results)
        user_prompt = f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER:"
        answer_text = self.llm.generate(SYSTEM_PROMPT, user_prompt).strip()
        tokens = estimate_tokens(SYSTEM_PROMPT, user_prompt, answer_text)

        return AnswerResult(
            question=question,
            answer=answer_text,
            confidence=confidence,
            escalate=False,
            sources=sources,
            tokens_used=tokens,
        )


def build_agent(config: Config, store: VectorStore | None = None) -> SupportAgent:
    """Convenience builder that loads/builds the index if needed."""
    from .ingest import load_or_build_index

    embedder = get_embedder(config)
    if store is None:
        store = load_or_build_index(config, embedder=embedder)
    return SupportAgent(config, store, embedder=embedder, llm=get_llm(config))
