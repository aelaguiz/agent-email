"""Which agent this is, which mailbox it sends from, and which folder an agent works in."""
import json
import os
from pathlib import Path

from . import config


def session():
    """How to reach the calling session, read from its own environment. Approvals' delivery code uses these fields."""
    env = os.environ
    if env.get("CLAUDE_CODE_SESSION_ID"):
        runtime, sid = "claude", env["CLAUDE_CODE_SESSION_ID"]
    elif env.get("CODEX_THREAD_ID"):
        runtime, sid = "codex", env["CODEX_THREAD_ID"]
    else:
        runtime, sid = None, None
    return {
        "agent": env.get("GIT_AUTHOR_NAME") or env.get("AGENT_ID") or Path.cwd().name,
        "agent_id": env.get("AGENT_ID"),
        "runtime": runtime,
        "session_id": sid,
        "cwd": os.getcwd(),
        "herdr_session": env.get("HERDR_SESSION"),
        "herdr_workspace": env.get("HERDR_WORKSPACE_ID"),
        "herdr_tab": env.get("HERDR_TAB_ID"),
        "herdr_pane": env.get("HERDR_PANE_ID"),
    }


def folder_rule(cwd, s):
    """The longest configured folder holding this working folder."""
    here = Path(os.path.realpath(cwd))
    best, length = None, -1
    for rule in s["folders"]:
        f = Path(os.path.realpath(os.path.expanduser(rule["path"])))
        if (here == f or f in here.parents) and len(f.parts) > length:
            best, length = rule, len(f.parts)
    if best is None:
        raise config.ConfigError(f"no folder rule covers {here}")
    return best


def has_mailbox(account, s):
    """Only the configured mailboxes and the owner's own accounts have Gmail. An agent's own Google login is a login only:
    Google routes mail for its address into a shared mailbox, and it sends from there."""
    return account in s["mailboxes"] or account in s["owner_accounts"]


def mailbox_for(agent_id, cwd, s=None):
    """(account, address, where his email goes). An agent sends from a configured mailbox that is its own (the account
    named for it, or one that names it), and otherwise from its folder's shared mailbox under its own name."""
    s = s or config.settings()
    rule = folder_rule(cwd, s)
    if agent_id and agent_id not in s["owner_accounts"]:
        named = [a for a, box in s["mailboxes"].items() if box.get("agent_id") == agent_id and a not in s["owner_accounts"]]
        for account in ([agent_id] if agent_id in s["mailboxes"] else []) + named:
            if config.grant_path(account, s).exists():
                return account, address_of(account, s), rule["to"]
    return rule["account"], address_of(rule["account"], s), rule["to"]


def address_of(account, s):
    box = s["mailboxes"].get(account) or {}
    return box.get("address") or f"{account}@{s['agent_domain']}"


def agent_folders(s=None):
    """Agent id to folder, from each repository's .agent-identities.json."""
    s = s or config.settings()
    out = {}
    for repo in s["agent_repos"]:
        repo = Path(os.path.expanduser(repo))
        path = repo / ".agent-identities.json"
        if path.exists():
            for rel, agent in json.loads(path.read_text()).get("folders", {}).items():
                out[agent] = str(repo / rel)
    return out


def known_folders(s=None):
    """Every folder that belongs to an agent, real path to agent id: each repository's agents, and each configured
    mailbox's folder."""
    s = s or config.settings()
    out = {os.path.realpath(f): agent for agent, f in agent_folders(s).items()}
    for account, box in s["mailboxes"].items():
        out.setdefault(os.path.realpath(os.path.expanduser(box["folder"])), box.get("agent_id") or account)
    return out


def mailboxes(s=None):
    """Every mailbox the system watches: the configured ones. Agents' own addresses have none."""
    s = s or config.settings()
    return [{"account": account, "address": box.get("address") or address_of(account, s),
             "own_mailbox": bool(box.get("own_mailbox")), "folder": os.path.expanduser(box["folder"]),
             "agent_id": box.get("agent_id") or account}
            for account, box in s["mailboxes"].items()]


def agent_for_address(address, s=None):
    """(agent id, folder) when an address is an agent's own, <agent id>@<agent_domain>, rather than a configured
    mailbox's. Google routes mail for those addresses into a shared mailbox, and this says whose it is."""
    s = s or config.settings()
    address = (address or "").strip().lower()
    local, _, domain = address.partition("@")
    if domain != s["agent_domain"].lower() or any(address_of(a, s).lower() == address for a in s["mailboxes"]):
        return None
    folder = agent_folders(s).get(local)
    return (local, folder) if folder else None


def agent_from_address(address, mailbox, s=None):
    """Who a new email to this address is for. chief+cfo-specialist@... names an agent with no mailbox of its own."""
    s = s or config.settings()
    local = address.split("@", 1)[0]
    if "+" not in local or mailbox["own_mailbox"]:
        return mailbox["agent_id"], mailbox["folder"]
    tag = local.split("+", 1)[1]
    folders = agent_folders(s)
    return tag, folders.get(tag, mailbox["folder"])
