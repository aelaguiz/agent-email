"""Where things live, and the settings shared by every machine.

config.json is the same everywhere. machine.json says which machine this is, because a machine's name has to stay
fixed: the name the operating system reports can change under a running service.
"""
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_EMAIL_HOME") or Path.home() / ".agent-email")
SENT = ROOT / "sent"
INBOUND = ROOT / "inbound"
INBOX = ROOT / "inbox"
LOGS = ROOT / "logs"
LOCK = ROOT / "store.lock"

DEFAULTS = {
    "owner": "the owner",
    "poll_seconds": 30,
    "unlabeled_wait_minutes": 3,     # how long a reply with no machine label waits before the home machine takes it
    "machine_off_minutes": 30,       # how long a reply waits on another machine before the owner hears why
    "warn_minutes": 15,              # how long an agent has to read and answer before the owner hears about it
    "herdr_session": "email",
    "start_command": "aim claude run opus",
    "machines": {},
    "agent_repos": [],
    "folders": [],
    "mailboxes": {},
    "owner_accounts": {},
}


class ConfigError(RuntimeError):
    pass


def settings():
    path = ROOT / "config.json"
    if not path.exists():
        raise ConfigError(f"{path} is missing; see config.example.json")
    return {**DEFAULTS, **json.loads(path.read_text())}


def machine():
    path = ROOT / "machine.json"
    if not path.exists():
        raise ConfigError(f"{path} is missing; run make install")
    return json.loads(path.read_text())


def grant_path(account, s=None):
    s = s or settings()
    return Path(os.path.expanduser(s["grants_dir"])) / f"gws-{account}-credentials.json"


def accounts(s=None):
    """Every account with a saved grant."""
    s = s or settings()
    folder = Path(os.path.expanduser(s["grants_dir"]))
    return sorted(p.name[len("gws-"):-len("-credentials.json")] for p in folder.glob("gws-*-credentials.json"))
