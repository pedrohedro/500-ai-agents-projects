"""End-to-end pipeline test in mock mode (ingest -> query -> billing)."""
import os


def test_full_pipeline_mock(config):
    from chatbot.agent import build_agent
    from chatbot.billing import BillingEngine

    os.environ["LLM_PROVIDER"] = "mock"
    agent = build_agent(config)
    billing = BillingEngine(config)
    billing.create_account("demo", plan_key="starter", seats=1)

    result = agent.answer("What plans do you offer?")
    charge = billing.charge_message("demo", result.tokens_used, answered=not result.escalate)

    assert result.answer
    assert result.sources
    if not result.escalate:
        assert charge.charged


def test_cli_ask_runs(capsys):
    os.environ["LLM_PROVIDER"] = "mock"
    from main import main

    exit_code = main(["ask", "How do I reset my password?"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "confidence" in out
    assert "billing" in out.lower()
