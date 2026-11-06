import json

import pytest

from agent_email import config


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A machine's agent-email folder, with one shared mailbox, one agent mailbox and an owner's own plus address."""
    root = tmp_path / ".agent-email"
    grants = tmp_path / "grants"
    repo = tmp_path / "brain"
    for d in (root, grants, repo / "pods/growth/lead", repo / "specialists/cfo"):
        d.mkdir(parents=True)
    (repo / ".agent-identities.json").write_text(json.dumps(
        {"folders": {"pods/growth/lead": "growth-lead", "specialists/cfo": "cfo-specialist"}}))
    for name in ("chief", "fc", "side", "growth-lead"):
        (grants / f"gws-{name}-credentials.json").write_text("{}")
    (root / "config.json").write_text(json.dumps({
        "owner": "Owner", "owner_addresses": ["owner@example.com", "owner@example.org", "owner@gmail.com"],
        "grants_dir": str(grants), "home_machine": "m5", "agent_domain": "example.com",
        "start_time": "2026-11-06T00:00:00+00:00",
        "owner_accounts": {"fc": None, "side": "owner+agent@example.net"},
        "agent_repos": [str(repo)],
        "folders": [{"path": str(tmp_path), "account": "chief", "to": "owner@gmail.com"},
                    {"path": str(repo), "account": "chief", "to": "owner@example.org"},
                    {"path": str(tmp_path / "cj"), "account": "side", "to": "owner@example.net"}],
        "mailboxes": {"chief": {"folder": str(repo)},
                      "side": {"address": "owner+agent@example.net", "own_mailbox": True, "folder": str(tmp_path / "cj")}}}))
    (root / "machine.json").write_text(json.dumps({"name": "m5", "gws_bin": "/bin/true"}))
    for name, value in (("ROOT", root), ("SENT", root / "sent"), ("INBOUND", root / "inbound"), ("INBOX", root / "inbox"),
                        ("LOGS", root / "logs"), ("LOCK", root / "store.lock")):
        monkeypatch.setattr(config, name, value)
    return tmp_path
