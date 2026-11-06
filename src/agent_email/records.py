"""What this machine remembers: which session sent each email, and each reply it owns.

Several processes touch these files (the listener, and agents running `agent-email read`), so changes go through a
lock and every write replaces the whole file, leaving a good copy on disk if anything dies part way.
"""
import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config


def now():
    return datetime.now(timezone.utc)


def iso(t=None):
    return (t or now()).isoformat(timespec="seconds")


def parse(text):
    return datetime.fromisoformat(text)


def minutes_since(text):
    return (now() - parse(text)).total_seconds() / 60


def write(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(record, indent=1))
    os.replace(tmp, path)


@contextmanager
def locked():
    config.ROOT.mkdir(parents=True, exist_ok=True)
    with open(config.LOCK, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def sent_path(account, gmail_id):
    return config.SENT / account / f"{gmail_id}.json"


def load_sent(account, gmail_id):
    path = sent_path(account, gmail_id)
    return json.loads(path.read_text()) if path.exists() else None


def all_sent(account=None):
    folders = [config.SENT / account] if account else config.SENT.glob("*")
    for folder in folders:
        for p in folder.glob("*.json"):
            yield json.loads(p.read_text())


def ref_for(gmail_id):
    return f"EM-{gmail_id}"


def inbound_path(ref):
    return config.INBOUND / f"{ref}.json"


def load_inbound(ref):
    path = inbound_path(ref)
    return json.loads(path.read_text()) if path.exists() else None


def all_inbound():
    for p in sorted(config.INBOUND.glob("EM-*.json")):
        yield json.loads(p.read_text())


def save_inbound(record):
    with locked():
        write(inbound_path(record["ref"]), record)


def update_inbound(ref, **changes):
    with locked():
        record = load_inbound(ref)
        if record is None:
            return None
        record.update(changes)
        write(inbound_path(ref), record)
        return record
