from datetime import timedelta
from types import SimpleNamespace

import pytest
import samples as s
from agent_email import cli, records
from test_listener import FakeAccount


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


@pytest.mark.parametrize("command", [
    ["send", "--subject", "News"],
    ["send", "--subject", "News", "--to", "team@example.com"],
    ["reply", "EM-m1"],
], ids=["send", "send-to-team", "reply"])
@pytest.mark.parametrize("purpose", [None, "yes", "nothing"])
def test_an_email_must_have_a_purpose_that_belongs_in_email(command, purpose, home, monkeypatch, capsys):
    argv = ["agent-email", *command, "--body", "News"]
    if purpose is not None:
        argv += ["--for", purpose]
    monkeypatch.setattr(cli.sys, "argv", argv)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: pytest.fail("ran a command before checking --for"))
    monkeypatch.setattr(cli, "Account", lambda *a: pytest.fail("opened Gmail before checking --for"))

    with pytest.raises(SystemExit) as result:
        cli.main()

    assert result.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    if purpose is None:
        assert output.err == cli.FOR_GUIDANCE + "\n"
    else:
        assert output.err.startswith(f"  --for {purpose} ") and len(output.err.splitlines()) == 1


@pytest.mark.parametrize("purpose", ["asked", "read", "problem"])
def test_an_email_with_an_allowed_purpose_sends_as_before(purpose, home, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.identity, "session", lambda: {"agent_id": "growth-lead", "cwd": str(home / "brain")})
    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Growth lead")
    monkeypatch.setattr(cli.sys, "argv", ["agent-email", "send", "--for", purpose, "--subject", "News",
                                        "--body", "**Update**", "--cc", "pat@example.net", "-a", "report.pdf"])

    with pytest.raises(SystemExit) as result:
        cli.main()

    assert result.value.code == 0
    assert calls == [([cli.gws("chief"), "gmail", "+send", "--to", "owner@example.org", "--subject", "News",
                       "--body", cli.compose.email("**Update**", signer="Growth lead"), "--html",
                       "--from", "Growth lead <chief@example.com>", "--cc", "pat@example.net", "-a", "report.pdf"], {})]


@pytest.fixture
def reply_command(home, monkeypatch):
    mailbox = FakeAccount()
    calls = []

    def account(name, settings):
        assert name == "chief"
        return mailbox

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli, "Account", account)
    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Growth lead")
    monkeypatch.setattr(cli.sys, "argv", ["agent-email", "reply", "EM-m1", "--for", "asked", "--body", "**Update**", "-a", "report.pdf"])
    return mailbox, calls


def test_a_reply_to_sent_mail_lets_gmail_keep_the_recipients(reply_command):
    mailbox, calls = reply_command
    original = {"gmail_id": "m1", "thread_id": "t1", "account": "chief", "reach": {"session_id": "old"}}
    records.write(records.sent_path("chief", "m1"), original)
    inbound = {"ref": "EM-r1", "account": "chief", "thread_id": "t1", "answered_at": None}
    records.save_inbound(inbound)
    mailbox.put("m1", s.h(From="Original Sender <growth+news@example.com>", To="Owner <owner@example.org>",
                          Cc="pat@example.net, growth+news@example.com"))

    with pytest.raises(SystemExit) as result:
        cli.main()

    assert result.value.code == 0
    assert calls == [([cli.gws("chief"), "gmail", "+reply-all", "--message-id", "m1", "--remove", "growth+news@example.com",
                       "--body", cli.compose.email("**Update**", signer="Growth lead"), "--html",
                       "--from", "Growth lead <growth+news@example.com>", "-a", "report.pdf"],
                      {"stdout": cli.subprocess.DEVNULL})]
    assert records.load_inbound("EM-r1") == inbound
    assert list(records.all_sent()) == [original]


def test_a_reply_to_inbound_mail_keeps_its_recipients_and_marks_it_answered(reply_command, monkeypatch):
    mailbox, calls = reply_command
    records.save_inbound({"ref": "EM-m1", "gmail_id": "m1", "account": "chief", "mailbox": "chief@example.com",
                          "reply_to": "owner@example.org", "answered_at": None})
    monkeypatch.setattr(records, "all_sent", lambda: pytest.fail("searched sent records for an inbound reference"))
    mailbox.put("m1", s.h(Delivered_To="chief+growth@example.com", From="owner@example.org",
                          To="chief+growth@example.com, sam@example.net", Cc="pat@example.net"))

    with pytest.raises(SystemExit) as result:
        cli.main()

    assert result.value.code == 0
    assert calls == [([cli.gws("chief"), "gmail", "+reply", "--message-id", "m1", "--to", "owner@example.org,sam@example.net",
                       "--body", cli.compose.email("**Update**", signer="Growth lead"), "--html",
                       "--from", "Growth lead <chief@example.com>", "--cc", "pat@example.net", "-a", "report.pdf"],
                      {"stdout": cli.subprocess.DEVNULL})]
    assert records.load_inbound("EM-m1")["answered_at"] is not None


def test_sent_shows_up_to_twenty_of_this_agents_emails_newest_first(home, monkeypatch, capsys):
    monkeypatch.setenv("AGENT_ID", "growth-lead")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Growth lead")
    monkeypatch.setattr(cli.sys, "argv", ["agent-email", "sent"])
    first = records.parse("2026-11-18T10:00:00+02:00")
    for n in range(22):
        account = "chief" if n % 2 else "growth-lead"
        records.write(records.sent_path(account, f"m{n}"), {
            "gmail_id": f"m{n}", "account": account, "sent_at": records.iso(first + timedelta(minutes=n)),
            "subject": f"Status\n {n}",
            "reach": {"agent_id": "growth-lead", "agent": "Previous name", "session_id": f"s{n}"}})
    records.write(records.sent_path("chief", "other"), {
        "gmail_id": "other", "account": "chief", "sent_at": records.iso(first + timedelta(days=1)),
        "subject": "Another agent's email", "reach": {"agent_id": "another-agent", "agent": "Growth lead"}})

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        f"EM-m{n}  {(first + timedelta(minutes=n)).astimezone():%m-%d %H:%M}  Status {n}"
        for n in range(21, 1, -1)]


def test_sent_uses_the_agents_name_without_an_id(home, monkeypatch, capsys):
    monkeypatch.delenv("AGENT_ID", raising=False)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Growth lead")
    monkeypatch.setattr(cli.sys, "argv", ["agent-email", "sent"])
    when = records.parse("2026-11-18T10:00:00+02:00")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "this-session")
    for gmail_id, reach in (("m1", {"agent": "Growth lead"}), ("m2", {"agent": "Another agent"}), ("m3", None),
                            ("m4", {"agent": "scratch", "session_id": "this-session"})):
        records.write(records.sent_path("chief", gmail_id), {
            "gmail_id": gmail_id, "account": "chief", "sent_at": records.iso(when), "reach": reach})

    cli.main()

    assert sorted(capsys.readouterr().out.splitlines()) == [f"EM-m{n}  {when.astimezone():%m-%d %H:%M}  " for n in (1, 4)]


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


def test_the_member_in_its_tab_reads_what_its_earlier_session_was_told_of_and_a_chat_in_its_folder_does_not(home, monkeypatch, capsys):
    from agent_email import records
    seat = {"pod_command": "/b/pod", "herdr_session": "pods", "pod": "growth", "copy": "lead"}
    records.save_inbound({"ref": "EM-r1", "subject": "Status", "reach": {"session_id": "old", "seat": seat},
                          "notified_at": records.iso(), "read_at": None})
    for sid, now, sees in (("chat", None, False), ("copy-2", dict(seat, copy="lead-2"), False), ("new", dict(seat), True)):
        monkeypatch.setattr(cli, "me_here", lambda sid=sid, now=now: {"session_id": sid, "seat": now})
        cli.cmd_inbox(None)
        assert ("EM-r1" in capsys.readouterr().out) == sees
