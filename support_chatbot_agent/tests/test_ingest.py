"""Tests for knowledge-base ingestion and chunking."""
from chatbot.ingest import build_index, chunk_text, load_documents


def test_chunk_text_produces_chunks():
    text = "\n\n".join(f"Paragraph number {i} with some content." for i in range(20))
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert all(isinstance(c, str) and c for c in chunks)


def test_chunk_text_empty():
    assert chunk_text("", 100, 20) == []


def test_load_documents_reads_sample_kb(config):
    docs = load_documents(config.knowledge_base_dir)
    names = {name for name, _ in docs}
    assert "getting_started.md" in names
    assert "security_and_privacy.txt" in names  # .txt files loaded too
    assert len(docs) >= 3


def test_build_index_embeds_chunks(config):
    store = build_index(config, persist=False)
    assert len(store) > 0
    # Every chunk must have a non-empty embedding of the configured dimension.
    for chunk in store.chunks:
        assert len(chunk.embedding) == config.embedding_dim
        assert chunk.source
        assert chunk.text


def test_index_persists_and_loads(config):
    from chatbot.vectorstore import VectorStore

    store = build_index(config, persist=True)
    assert VectorStore.exists(config.index_path)
    reloaded = VectorStore.load(config.index_path)
    assert len(reloaded) == len(store)
