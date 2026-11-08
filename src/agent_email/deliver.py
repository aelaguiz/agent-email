"""Telling a session it has email. Finding, resuming and typing into a session is approvals' code, which has already
been through real use. This adds what approvals never needs: starting a new session for an agent."""
import os
import shlex
import time

import approvals.config
from approvals import router, transcripts

from . import config, records

READY_SECONDS = 180
CONFIRM_SECONDS = 90
TRUST_PROMPT = "Yes, I trust this folder"


def _use_our_settings():
    """Approvals reads its default Herdr session from its own config folder. Point it at ours."""
    folder = config.ROOT / "approvals-settings"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "config.json").write_text('{"default_herdr_session": "%s"}' % herdr_session())
    approvals.config.use(folder)


def herdr_session():
    return config.machine().get("herdr_session") or config.settings()["herdr_session"]


def ensure_herdr(session):
    """A headless Herdr server for sessions this tool starts or resumes: approvals' own, which its delivery uses too."""
    router.ensure_herdr(session)


def tell_session(item, notice):
    """A reply to an email a session sent, or an agent with one running session: approvals' delivery does it all."""
    _use_our_settings()
    ensure_herdr(herdr_session())
    reach = dict(item["reach"])
    reach["host"] = approvals.config.hostname()      # ownership is already settled, so this is always this machine
    reach["tab_label"] = "email"
    return router.deliver(reach, notice, item["ref"], request_id=item.get("sent_id") or item["ref"])


def running_session(folder):
    """The one Claude session running in this folder, or None if there are none or several."""
    found = [(sid, cwd) for _, sid, cwd in transcripts.live_sessions("claude")
             if cwd and os.path.realpath(cwd) == os.path.realpath(folder)]
    return found[0][0] if len(found) == 1 else None


def accept_trust(h, pane):
    h.call("pane", "send-keys", pane, "Down", "Enter")


def start_session(item, notice, sleep=time.sleep, clock=time.monotonic):
    """A new session in the agent's folder, opened in its own tab, with the notice as its first message."""
    _use_our_settings()
    session = herdr_session()
    ensure_herdr(session)
    h = router.Herdr(session)
    folder = item["folder"]
    label = f"email-{item.get('agent_id') or 'agent'}"[:40]
    workspaces = h.workspaces()
    pane, tab, workspace = h.new_tab(workspaces[0], folder, label) if workspaces else h.new_workspace(folder, "email")
    command = f"cd {shlex.quote(folder)} && AGENT_ID={shlex.quote(item.get('agent_id') or '')} {config.settings()['start_command']}"
    h.run_cmd(pane, command)
    start = clock()
    while clock() - start < READY_SECONDS:
        sleep(3)
        screen = h.read(pane, 15)
        if TRUST_PROMPT in screen:      # a folder in the owner's config, on an account that hasn't opened it before
            accept_trust(h, pane)
            continue
        sid = router._claude_sid_in_pane(h, pane)
        if sid and "bypass permissions" in screen:
            break
    else:
        h.close(pane)
        return router.Result("retry", "the new session didn't come up")
    # Saved before the notice goes in, so a retry uses this session rather than starting another.
    records.update_inbound(item["ref"], reach={
        "agent": item.get("agent_id"), "runtime": "claude", "session_id": sid, "cwd": folder, "herdr_session": session,
        "herdr_workspace": workspace, "herdr_tab": tab, "herdr_pane": pane})
    sleep(2)
    h.send(pane, notice)
    start = clock()
    while clock() - start < CONFIRM_SECONDS:
        if transcripts.contains(transcripts.transcript("claude", sid), item["ref"]):
            return router.Result("delivered", "seen in the transcript")
        sleep(3)
    return router.Result("retry", "sent, but not seen in the transcript yet")


def deliver(item, notice):
    if item.get("reach"):
        return tell_session(item, notice)
    sid = running_session(item["folder"])
    if sid:
        records.update_inbound(item["ref"], reach={"agent": item.get("agent_id"), "runtime": "claude", "session_id": sid,
                                                   "cwd": item["folder"]})
        item = {**item, "reach": records.load_inbound(item["ref"])["reach"]}
        return tell_session(item, notice)
    return start_session(item, notice)
