from unittest.mock import Mock

from agent_email import deliver


def test_new_session_gets_its_own_labeled_workspace(monkeypatch):
    h = Mock()
    h.workspaces.return_value = ["existing-workspace"]
    h.new_workspace.return_value = ("pane", "tab", "new-workspace")
    h.read.return_value = "bypass permissions"
    monkeypatch.setattr(deliver, "_use_our_settings", lambda: None)
    monkeypatch.setattr(deliver, "herdr_session", lambda: "herdr")
    monkeypatch.setattr(deliver, "ensure_herdr", lambda session: None)
    monkeypatch.setattr(deliver.router, "Herdr", lambda session: h)
    monkeypatch.setattr(deliver.router, "_claude_sid_in_pane", lambda h, pane: "session")
    monkeypatch.setattr(deliver.config, "settings", lambda: {"start_command": "claude"})
    monkeypatch.setattr(deliver.records, "update_inbound", lambda *args, **kwargs: None)
    monkeypatch.setattr(deliver.transcripts, "transcript", lambda runtime, sid: "transcript")
    monkeypatch.setattr(deliver.transcripts, "contains", lambda transcript, ref: True)

    result = deliver.start_session({"folder": "/agent", "agent_id": "cfo", "ref": "EM-1"}, "notice",
                                   sleep=lambda seconds: None, clock=lambda: 0)

    assert result.status == "delivered"
    h.new_workspace.assert_called_once_with("/agent", "email-cfo")
    h.new_tab.assert_not_called()


def test_a_pod_members_new_email_goes_to_its_tab_and_waits_while_nothing_runs_there(monkeypatch):
    """A pod member is its tab (approvals' pods.py): never a new session beside it, never a chat in its folder."""
    seat = {"pod_command": "/b/pod", "herdr_session": None, "pod": "growth", "copy": "lead"}
    told, saved = [], {}
    monkeypatch.setattr(deliver, "start_session", lambda item, notice: told.append("started"))
    monkeypatch.setattr(deliver, "tell_session", lambda item, notice: told.append(item["reach"]) or "told")
    monkeypatch.setattr(deliver.router, "find_pane_for_pid", lambda pid: ("pods", "w2:p1"))
    monkeypatch.setattr(deliver.records, "update_inbound", lambda ref, reach: saved.update(reach))
    monkeypatch.setattr(deliver.records, "load_inbound", lambda ref: {"reach": dict(saved)})
    item = {"ref": "EM-1", "folder": "/b/pods/growth/lead", "agent_id": "growth-lead"}
    monkeypatch.setattr(deliver.pods, "in_folder", lambda folder: [])
    assert deliver.deliver(item, "notice").status == "waiting" and not told
    monkeypatch.setattr(deliver.pods, "in_folder", lambda folder: [(seat, "claude", "s1", 11), (dict(seat, copy="lead-2"), "claude", "s2", 12)])
    assert deliver.deliver(item, "notice") == "told"
    assert (told[0]["session_id"], told[0]["herdr_pane"], told[0]["seat"]) == ("s1", "w2:p1", dict(seat, herdr_session="pods"))
