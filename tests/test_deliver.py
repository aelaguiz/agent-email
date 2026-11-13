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
