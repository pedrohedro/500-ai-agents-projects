"""Tests for the vector store retrieval quality (mock embeddings)."""
from chatbot.llm import MockEmbedder
from chatbot.vectorstore import Chunk, VectorStore


def test_mock_embedder_deterministic():
    emb = MockEmbedder(dim=128)
    a = emb.embed_one("reset my password")
    b = emb.embed_one("reset my password")
    assert a == b  # same text -> identical vector
    assert len(a) == 128


def test_search_returns_relevant_chunk(config, store):
    emb = MockEmbedder(dim=config.embedding_dim)
    q = emb.embed_one("How do I reset my password?")
    results = store.search(q, top_k=3)
    assert results
    # The password-reset content lives in getting_started.md and should surface.
    top_text = " ".join(r.chunk.text.lower() for r in results)
    assert "password" in top_text


def test_search_scores_descending(store):
    emb = MockEmbedder(dim=len(store.chunks[0].embedding))
    q = emb.embed_one("refund policy money back guarantee")
    results = store.search(q, top_k=4)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_empty_store_returns_nothing():
    store = VectorStore([])
    assert store.search([0.1, 0.2, 0.3], top_k=3) == []
