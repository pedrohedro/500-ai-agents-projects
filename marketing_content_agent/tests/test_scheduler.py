"""Tests for the automation layer (cron loop) in MOCK mode."""

from marketing_content_agent.billing import Wallet
from marketing_content_agent.config import get_settings
from marketing_content_agent.scheduler import run_cron_loop, run_once
from marketing_content_agent.schemas import ContentBrief


def test_run_once():
    d = run_once(ContentBrief(topic="Scheduler test"))
    assert d.blog_post.strip()


def test_cron_loop_processes_briefs():
    briefs = [
        {"topic": "Topic A", "target_audience": "devs"},
        {"topic": "Topic B", "target_audience": "founders"},
    ]
    results = run_cron_loop(
        lambda: briefs,
        interval_seconds=0,
        max_iterations=1,
        sleep=lambda s: None,
    )
    assert len(results) == 2
    assert all(r.qa.passed for r in results)


def test_cron_loop_stops_when_out_of_credits():
    briefs = [{"topic": "T1"}, {"topic": "T2"}, {"topic": "T3"}]
    per_gen = get_settings().credits_per_generation
    wallet = Wallet(balance=per_gen)  # only enough for one generation
    results = run_cron_loop(
        lambda: briefs,
        interval_seconds=0,
        max_iterations=1,
        wallet=wallet,
        sleep=lambda s: None,
    )
    assert len(results) == 1
    assert wallet.balance == 0


def test_cron_loop_skips_malformed_briefs():
    briefs = [{"no_topic": "x"}, {"topic": "Valid"}]
    results = run_cron_loop(
        lambda: briefs,
        interval_seconds=0,
        max_iterations=1,
        sleep=lambda s: None,
    )
    assert len(results) == 1
