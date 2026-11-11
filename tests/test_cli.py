import pytest
import samples as s
from agent_email import cli


def test_an_answer_goes_to_everyone_on_his_email_but_the_agent():
    """His reply-all keeps its To and Cc lists, without the agent's mailbox or the plus address his email reached it at."""
    headers = s.h(Delivered_To="chief+cfo@example.com", From="Owner Name <owner@example.org>",
                  To='Chief <chief@example.com>, "Lee, Sam" <sam@example.net>, chief+cfo@example.com',
                  Cc="pat@example.net, Owner Name <OWNER@example.org>")
    item = {"reply_to": "owner@example.org", "mailbox": "chief@example.com"}
    assert cli.recipients(item, headers) == (["owner@example.org", "sam@example.net"], ["pat@example.net"])


def test_a_reply_to_the_agent_alone_is_answered_to_him_alone():
    item = {"reply_to": "owner@example.org", "mailbox": "agent@example.com"}
    assert cli.recipients(item, s.DEFAULT_SENDER) == (["owner@example.org"], [])


def handed(home, monkeypatch, running_folder=None, machines=None):
    import json as _json
    from types import SimpleNamespace
    from approvals import transcripts
    from agent_email import config, records
    path = config.ROOT / "config.json"
    cfg = _json.loads(path.read_text())
    cfg["machines"] = machines or {}
    path.write_text(_json.dumps(cfg))
    monkeypatch.setattr(transcripts, "live_sessions",
                        lambda runtime: [(1, "s9", str(running_folder))] if running_folder else [])
    records.save_inbound({"ref": "EM-x1", "gmail_id": "x1", "thread_id": "t1", "kind": "unmatched", "account": "chief",
                          "mailbox": "chief@example.com", "subject": "Status", "reply_to": "owner@example.com",
                          "agent_id": "chief", "folder": str(home / "brain"), "sent_id": None, "reach": {"session_id": "s1"},
                          "received_at": records.iso(), "attempts": 2, "next_try": records.iso(),
                          "notified_at": records.iso(), "read_at": records.iso(), "answered_at": None, "warned": False})
    return SimpleNamespace(ref="EM-x1", agent="growth-lead")


def test_a_handoff_to_an_agent_running_here_becomes_its_own_email(home, monkeypatch):
    from agent_email import records
    a = handed(home, monkeypatch, running_folder=home / "brain/pods/growth/lead")
    cli.cmd_handoff(a)
    item = records.load_inbound("EM-x1")
    assert item["agent_id"] == "growth-lead" and item["kind"] == "handoff" and item["folder"].endswith("pods/growth/lead")
    assert item["reach"] is None and not item["notified_at"] and not item["read_at"] and item["handed_from"] == "chief"


def test_a_handoff_goes_to_the_machine_the_agent_runs_on(home, monkeypatch):
    import json as _json
    from types import SimpleNamespace
    from agent_email import records
    a = handed(home, monkeypatch, machines={"studio": "me@studio"})
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd[-1], kw.get("input")))
        return SimpleNamespace(returncode=0, stdout="yes\n" if "running" in cmd[-1] else "", stderr="")
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    cli.cmd_handoff(a)
    adopted = _json.loads(next(i for c, i in calls if c.endswith("adopt")))
    assert adopted["agent_id"] == "growth-lead" and adopted["kind"] == "handoff"
    assert records.load_inbound("EM-x1") is None


def test_repoint_sends_replies_for_a_saved_session_to_the_restored_one(home, monkeypatch, capsys):
    from approvals import router, transcripts
    from agent_email import records
    monkeypatch.setattr(transcripts, "live_sessions", lambda runtime: [(7, "new", "/pods/ai/lead")] if runtime == "claude" else [])
    monkeypatch.setattr(router, "find_pane_for_pid", lambda pid: ("pods", "w9:p1") if pid == 7 else None)
    old = {"runtime": "claude", "session_id": "old", "cwd": "/pods/ai/lead", "herdr_pane": "w4:p1", "agent": "AI lead"}
    records.write(records.sent_path("ai-lead", "g1"), {"gmail_id": "g1", "reach": dict(old)})
    records.write(records.sent_path("ai-lead", "g2"), {"gmail_id": "g2", "reach": dict(old, session_id="other")})
    records.save_inbound({"ref": "EM-r1", "reach": dict(old), "notified_at": None, "read_at": None})
    records.save_inbound({"ref": "EM-r2", "reach": dict(old), "notified_at": records.iso(), "read_at": records.iso()})
    cli.cmd_repoint(type("A", (), {"old": "old", "new": "new"}))
    r = records.load_sent("ai-lead", "g1")["reach"]
    assert (r["session_id"], r["herdr_pane"], r["agent"], r["earlier_ids"]) == ("new", "w9:p1", "AI lead", ["old"])
    assert records.load_sent("ai-lead", "g2")["reach"]["session_id"] == "other"
    assert records.load_inbound("EM-r1")["reach"]["session_id"] == "new"
    assert records.load_inbound("EM-r2")["reach"]["session_id"] == "old"     # already read by the old session
    assert "1 sent emails and 1 waiting" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.cmd_repoint(type("A", (), {"old": "new", "new": "old"}))      # "old" isn't running here
