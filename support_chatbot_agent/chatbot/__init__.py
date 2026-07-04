"""24/7 Support Chatbot Agent - a RAG-based, monetizable support assistant.

This package contains the core building blocks:

- ``config``       : environment-driven configuration.
- ``llm``          : provider interfaces for LLM + embeddings (OpenAI + Mock).
- ``vectorstore``  : a tiny local numpy cosine-similarity vector store.
- ``ingest``       : knowledge-base loading, chunking and embedding.
- ``agent``        : the RAG answer agent + escalation / QA gate.
- ``billing``      : credit / seat based monetization primitives.
"""

__version__ = "0.1.0"
