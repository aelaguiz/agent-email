import json
from types import SimpleNamespace

from approvals import router, transcripts

from agent_email import cli, deliver, identity, listener, records

SID_A = "11111111-1111-4111-8111-111111111111"
SID_B = "22222222-2222-4222-8222-222222222222"


def test_identity_session_captures_antigravity_env_and_model_without_secrets(monkeypatch, tmp_path):
    shim = tmp_path / ".local/share/agent-identity/bin"
    shim.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("ANTIGRAVITY_CONVERSATION_ID", SID_A)
    monkeypatch.setenv("BASECAMP_PROFILE", "demo-lead")
    monkeypatch.setenv("APPROVALS_FROM", "Demo Lead")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Demo Lead (agent)")
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "never-save-me")
    monkeypatch.setenv("PATH", f"{shim}:/usr/bin")
    monkeypatch.setattr(identity, "_agy_ancestor_model_effort", lambda: ("gemini-4-neon", "xhigh"))

    got = identity.session()
    assert (got["runtime"], got["session_id"], got["model"], got["effort"], got["agent_identity_bin"]) == (
        "agy", SID_A, "gemini-4-neon", "xhigh", True
    )
    assert got["env"] == {
        "APPROVALS_FROM": "Demo Lead",
        "GIT_AUTHOR_NAME": "Demo Lead (agent)",
    }
    assert "SUPER_SECRET_TOKEN" not in str(got)


def test_tell_session_confirms_real_notice_in_real_transcript(home, monkeypatch):
    """Real transcripts.typed/contains check: notices end with `agent-email read <ref>`, not `(ref <ref>)`."""
    transcript_file = home / f"{SID_A}.jsonl"
    transcript_file.write_text("")
    monkeypatch.setattr(deliver, "_use_our_settings", lambda: None)
    monkeypatch.setattr(deliver, "ensure_herdr", lambda session: None)
    monkeypatch.setattr(transcripts, "transcript", lambda rt, sid: str(transcript_file))
    monkeypatch.setattr(transcripts, "stopped_for_usage", lambda rt, sid: False)
    monkeypatch.setattr(transcripts, "claude_session_for_pid", lambda pid: SID_A if pid == 1 else None)
    monkeypatch.setattr(transcripts, "live_sessions", lambda rt: [])

    notice = listener.notice_for({"ref": "EM-real1", "kind": "reply", "subject": "Budget check"}, {"owner": "Owner"})
    assert not transcripts.typed(str(transcript_file), "EM-real1")

    def fake_herdr(cmd, **kw):
        args = cmd[3:]
        if args[:2] == ["pane", "get"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": {"pane": {"focused": False}}}), stderr="")
        if args[:2] == ["pane", "process-info"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": {"process_info": {"foreground_processes": [{"pid": 1}]}}}), stderr="")
        if args[:2] == ["pane", "read"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:2] == ["agent", "prompt"]:
            transcript_file.write_text(json.dumps({"type": "user", "message": {"content": args[3]}}) + "\n")
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    orig_deliver = router.deliver
    monkeypatch.setattr(router, "deliver", lambda *a, **kw: orig_deliver(*a, run=fake_herdr, sleep=lambda _: None, **kw))
    item = {
        "ref": "EM-real1", "sent_id": "g1",
        "reach": {"runtime": "claude", "session_id": SID_A, "cwd": str(home), "herdr_session": "default", "herdr_pane": "w1:p1"},
    }
    res = deliver.tell_session(item, notice)
    assert res.status == "delivered"
    # Confirming with approvals' default `(ref ...)` form would have failed, proving `needle` is required.
    assert not router.already_delivered(item["reach"], "EM-real1")
    # With the notice needle, a second try sees the notice already in the transcript and does not re-type it.
    assert router.already_delivered(item["reach"], "EM-real1", needle="agent-email read EM-real1") is True


def test_running_session_prefers_claude_and_routes_non_claude_when_alone(home, monkeypatch):
    folder = str(home / "brain/pods/growth/lead")
    # One Claude session plus an interactive Antigravity session in the same folder still picks Claude.
    monkeypatch.setattr(transcripts, "live_sessions", lambda rt: (
        [(10, SID_A, folder)] if rt == "claude" else [(20, SID_B, folder)] if rt == "agy" else []
    ))
    assert deliver.running_session(folder) == ("claude", SID_A)

    # Two Claude sessions stay ambiguous (None) and do not fall through to another runtime.
    monkeypatch.setattr(transcripts, "live_sessions", lambda rt: (
        [(10, SID_A, folder), (11, SID_B, folder)] if rt == "claude" else [(20, "s3", folder)] if rt == "agy" else []
    ))
    assert deliver.running_session(folder) is None

    # Alone, a single Antigravity session gets new mail with runtime="agy".
    monkeypatch.setattr(transcripts, "live_sessions", lambda rt: [(20, SID_B, folder)] if rt == "agy" else [])
    assert deliver.running_session(folder) == ("agy", SID_B)

    records.save_inbound({"ref": "EM-agy1", "agent_id": "growth-lead", "folder": folder, "reach": None})
    seen = {}
    monkeypatch.setattr(deliver, "tell_session", lambda item, notice: (seen.update(reach=item["reach"]), router.Result("delivered", "ok"))[1])
    res = deliver.deliver(records.load_inbound("EM-agy1"), "notice")
    assert res.status == "delivered" and seen["reach"]["runtime"] == "agy" and seen["reach"]["session_id"] == SID_B


def test_deliver_one_persists_moves_and_repoints_sent_even_on_retry(home, monkeypatch):
    folder = str(home / "brain/pods/growth/lead")
    old_reach = {"runtime": "codex", "session_id": SID_A, "cwd": folder, "herdr_session": "pods", "herdr_pane": "w1:p1",
                 "env": {"APPROVALS_FROM": "growth-lead"}}
    records.write(records.sent_path("chief", "g1"), {"gmail_id": "g1", "reach": dict(old_reach)})
    records.save_inbound({
        "ref": "EM-m1", "gmail_id": "m1", "thread_id": "t1", "kind": "reply", "account": "chief",
        "mailbox": "chief@example.com", "subject": "Check", "reply_to": "owner@example.com",
        "agent_id": "growth-lead", "folder": folder, "sent_id": "g1", "reach": dict(old_reach),
        "received_at": records.iso(), "attempts": 0, "next_try": records.iso(),
        "notified_at": None, "read_at": None, "answered_at": None, "warned": False,
    })
    monkeypatch.setattr(deliver, "deliver", lambda item, notice: router.Result(
        "retry", "sent, but not seen in the transcript yet",
        reach={"session_id": SID_B, "herdr_session": "pods", "herdr_pane": "w1:p9", "herdr_workspace": "w1"},
        moves=[[SID_A, SID_B]],
    ))
    l = listener.Listener()
    l.deliver_one("EM-m1")

    inb = records.load_inbound("EM-m1")
    assert inb["reach"]["session_id"] == SID_B
    assert inb["reach"]["herdr_pane"] == "w1:p9"
    assert inb["reach"]["earlier_ids"] == [SID_A]
    assert inb["reach"]["env"] == {"APPROVALS_FROM": "growth-lead"}

    sent = records.load_sent("chief", "g1")
    assert sent["reach"]["session_id"] == SID_B
    assert sent["reach"]["herdr_pane"] == "w1:p9"
    assert sent["reach"]["earlier_ids"] == [SID_A]


def test_listener_and_cli_recognize_running_agy_and_codex_sessions(home, monkeypatch):
    folder = home / "brain/pods/growth/lead"
    monkeypatch.setattr(transcripts, "live_sessions",
                        lambda rt: [(10, SID_A, str(folder))] if rt == "agy" else [])
    assert cli.runs_here(str(folder)) is True

    l = listener.Listener()
    folders, accounts = l.agents_running_here()
    assert str(folder.resolve()) in folders
    assert "chief" in accounts


def test_repoint_switches_runtime_to_running_agy_session(home, monkeypatch):
    monkeypatch.setattr(transcripts, "live_sessions",
                        lambda rt: [(10, SID_B, "/pods/ai/lead")] if rt == "agy" else [])
    monkeypatch.setattr(router, "find_pane_for_pid", lambda pid: ("pods", "w9:p1") if pid == 10 else None)
    old = {"runtime": "claude", "session_id": SID_A, "cwd": "/pods/ai/lead", "herdr_pane": "w4:p1", "agent": "AI lead"}
    records.write(records.sent_path("ai-lead", "g1"), {"gmail_id": "g1", "reach": dict(old)})
    records.save_inbound({"ref": "EM-r1", "reach": dict(old), "notified_at": None, "read_at": None})

    cli.cmd_repoint(SimpleNamespace(old=SID_A, new=SID_B))
    r = records.load_sent("ai-lead", "g1")["reach"]
    assert (r["runtime"], r["session_id"], r["herdr_pane"], r["earlier_ids"]) == ("agy", SID_B, "w9:p1", [SID_A])
    assert records.load_inbound("EM-r1")["reach"]["runtime"] == "agy"
