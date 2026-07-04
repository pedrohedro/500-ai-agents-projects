"""Tests for the automation / scheduler layer (batch inbox processing)."""
import os

from billing import BillingManager, CreditAccount
from config import get_settings
from scheduler import process_inbox


def _make_settings(tmp_path):
    settings = get_settings()
    settings.inbox_dir = str(tmp_path / "inbox")
    settings.outbox_dir = str(tmp_path / "outbox")
    os.makedirs(settings.inbox_dir, exist_ok=True)
    os.makedirs(settings.outbox_dir, exist_ok=True)
    return settings


SAMPLE = (
    "1. CONFIDENTIALITY. Keep information confidential in perpetuity. "
    "2. PAYMENT. Net 90, non-refundable. 3. LIABILITY. Unlimited liability."
)


def test_batch_processes_inbox_files(tmp_path):
    settings = _make_settings(tmp_path)
    with open(os.path.join(settings.inbox_dir, "contract1.txt"), "w") as fh:
        fh.write(SAMPLE)

    results = process_inbox(settings)
    assert len(results) == 1
    assert results[0]["status"] == "ok"
    assert os.path.isfile(results[0]["json_output"])
    assert os.path.isfile(results[0]["markdown_output"])
    # Processed file was moved out of the inbox.
    assert not os.path.isfile(os.path.join(settings.inbox_dir, "contract1.txt"))
    assert os.path.isfile(os.path.join(settings.inbox_dir, "_processed", "contract1.txt"))


def test_batch_blocks_when_out_of_credits(tmp_path):
    settings = _make_settings(tmp_path)
    with open(os.path.join(settings.inbox_dir, "contract2.txt"), "w") as fh:
        fh.write(SAMPLE)

    billing = BillingManager(CreditAccount(balance=0.0), settings)
    results = process_inbox(settings, billing)
    assert results[0]["status"] == "blocked"
    # File stays in inbox for retry after top-up.
    assert os.path.isfile(os.path.join(settings.inbox_dir, "contract2.txt"))


def test_batch_ignores_unsupported_files(tmp_path):
    settings = _make_settings(tmp_path)
    with open(os.path.join(settings.inbox_dir, "note.csv"), "w") as fh:
        fh.write("a,b,c")
    results = process_inbox(settings)
    assert results == []
