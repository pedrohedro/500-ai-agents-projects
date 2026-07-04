"""Tests for the RAG answer agent: grounding + escalation gate."""
from chatbot.agent import SupportAgent


def test_answer_is_grounded_with_sources(config, store):
    agent = SupportAgent(config, store)
    result = agent.answer("How do I reset my password?")

    assert not result.escalate
    assert result.confidence >= config.confidence_threshold
    assert result.sources, "grounded answers must cite sources"
    # The mock LLM is extractive, so the answer text must come from the KB.
    assert "password" in result.answer.lower()
    assert result.tokens_used > 0


def test_low_confidence_triggers_escalation(config, store):
    # An unrelated, out-of-domain question should fall below threshold.
    agent = SupportAgent(config, store)
    result = agent.answer("What is the airspeed velocity of an unladen swallow?")
    assert result.escalate
    assert "human" in result.answer.lower()


def test_high_threshold_forces_escalation(config, store):
    # Force escalation by making the threshold impossible to meet.
    config.confidence_threshold = 1.5
    agent = SupportAgent(config, store)
    result = agent.answer("How do I reset my password?")
    assert result.escalate


def test_empty_question_escalates(config, store):
    agent = SupportAgent(config, store)
    result = agent.answer("   ")
    assert result.escalate


def test_answer_to_dict_serializable(config, store):
    agent = SupportAgent(config, store)
    d = agent.answer("How do I cancel my subscription?").to_dict()
    assert set(d) >= {"question", "answer", "confidence", "escalate", "sources", "tokens_used"}
    assert isinstance(d["sources"], list)
