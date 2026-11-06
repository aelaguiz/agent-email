"""The real script, run with a fake gws, under the oldest Python it has to support."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "bin" / "gws-account"
PYTHON = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else shutil.which("python3")


@pytest.fixture
def world(tmp_path):
    root, grants, bin_dir = tmp_path / ".agent-email", tmp_path / "grants", tmp_path / "bin"
    for d in (root, grants, bin_dir, tmp_path / ".local" / "bin"):
        d.mkdir(parents=True)
    fake = bin_dir / "real-gws"
    fake.write_text('#!/bin/sh\necho "$@" > "$HOME/called"\nenv > "$HOME/env"\n'
                    'echo \'{"id":"m1","threadId":"t1"}\'\nexit ${FAKE_EXIT:-0}\n')
    fake.chmod(0o755)
    # A stand-in for agent-email, so the test can see the record being asked for.
    rec = tmp_path / ".local" / "bin" / "agent-email"
    rec.write_text('#!/bin/sh\necho "$@" > "$HOME/recorded"\n')
    rec.chmod(0o755)
    (root / "config.json").write_text(json.dumps({
        "grants_dir": str(grants), "agent_domain": "example.com",
        "owner_addresses": ["owner@example.com", "owner@example.org"], "default_account": "fc",
        "owner_accounts": {"fc": None, "side": "owner+agent@example.org"}}))
    (root / "machine.json").write_text(json.dumps({"name": "m5", "gws_bin": str(fake)}))
    for account in ("chief", "fc", "side", "growth-lead"):
        (grants / f"gws-{account}-credentials.json").write_text("{}")
    for name in ("gws", "gws-chief", "gws-fc", "gws-side", "gws-growth-lead", "gws-nobody"):
        (bin_dir / name).symlink_to(SCRIPT)
    return tmp_path


def run(world, name, *args, **env):
    full = {"HOME": str(world), "PATH": os.environ["PATH"], "AGENT_EMAIL_HOME": str(world / ".agent-email"), **env}
    return subprocess.run([PYTHON, str(world / "bin" / name), *args], env=full, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL)


def called(world):
    return (world / "called").read_text().strip()


def wait_for_record(world):
    for _ in range(25):
        if (world / "recorded").exists():
            return (world / "recorded").read_text()
        time.sleep(0.02)
    return None


def test_the_called_name_picks_the_grant(world):
    run(world, "gws-growth-lead", "drive", "files", "list")
    env = (world / "env").read_text()
    assert "gws-growth-lead-credentials.json" in env and "KEYRING_BACKEND=file" in env


def test_an_account_with_no_grant_refuses(world):
    r = run(world, "gws-nobody", "drive", "files", "list")
    assert r.returncode == 78 and "no saved grant" in r.stderr and not (world / "called").exists()


def test_bare_gws_is_the_owner_and_follows_the_profile(world):
    run(world, "gws", "drive", "files", "list")
    assert "gws-fc-credentials" in (world / "env").read_text()
    run(world, "gws", "drive", "files", "list", GWS_PROFILE="side")
    assert "gws-side-credentials" in (world / "env").read_text()
    assert run(world, "gws", "drive", GWS_PROFILE="nope").returncode == 78


def test_login_is_refused(world):
    assert run(world, "gws-chief", "auth", "login").returncode == 78


def test_a_non_send_is_left_alone_and_records_nothing(world):
    r = run(world, "gws-chief", "gmail", "users", "messages", "list", CLAUDE_CODE_SESSION_ID="s1", GIT_AUTHOR_NAME="Tech lead (agent)")
    assert called(world) == "gmail users messages list" and r.returncode == 0
    assert wait_for_record(world) is None


def test_a_send_keeps_stdout_and_exit_code_and_saves_a_record(world):
    r = run(world, "gws-chief", "gmail", "+send", "--to", "owner@example.com")
    assert json.loads(r.stdout)["id"] == "m1" and r.returncode == 0
    assert "--account chief --kind +send" in wait_for_record(world)


def test_a_failed_send_keeps_its_exit_code_and_records_nothing(world):
    r = run(world, "gws-chief", "gmail", "+send", "--to", "x@y.z", FAKE_EXIT="3")
    assert r.returncode == 3 and wait_for_record(world) is None


def test_a_broken_recorder_never_fails_the_send(world):
    (world / ".local" / "bin" / "agent-email").unlink()
    assert run(world, "gws-chief", "gmail", "+send", "--to", "x@y.z").returncode == 0


@pytest.mark.parametrize("args", [("gmail", "+send", "--to", "a@b.c", "--dry-run"), ("gmail", "+send", "--to", "a@b.c", "--draft")])
def test_nothing_is_recorded_for_a_draft_or_dry_run(world, args):
    run(world, "gws-chief", *args)
    assert wait_for_record(world) is None


def test_raw_sends_are_recorded(world):
    run(world, "gws-chief", "gmail", "users", "messages", "send", "--json", "{}")
    assert "users messages send" in wait_for_record(world)


def session(**extra):
    return {"CLAUDE_CODE_SESSION_ID": "s1", "GIT_AUTHOR_NAME": "Tech lead (agent)", **extra}


def test_an_agent_mailbox_gets_the_agents_name(world):
    run(world, "gws-chief", "gmail", "+send", "--to", "owner@example.com", **session())
    assert called(world).endswith("--from Tech lead (agent) <chief@example.com>")


def test_a_generic_name_leaves_the_mailbox_as_it_is(world):
    run(world, "gws-chief", "gmail", "+send", "--to", "owner@example.com", **session(GIT_AUTHOR_NAME="Claude (agent)"))
    assert "--from" not in called(world)


def test_outside_a_session_nothing_is_added(world):
    run(world, "gws-chief", "gmail", "+send", "--to", "owner@example.com", GIT_AUTHOR_NAME="Tech lead (agent)")
    assert "--from" not in called(world)


def test_an_explicit_from_is_kept(world):
    run(world, "gws-chief", "gmail", "+send", "--to", "a@b.c", "--from", "x@y.z", **session())
    assert called(world).count("--from") == 1 and "x@y.z" in called(world)


def test_the_owners_own_account_is_never_rewritten(world):
    run(world, "gws-fc", "gmail", "+send", "--to", "owner@example.com", **session())
    assert "--from" not in called(world)


def test_an_owner_account_with_an_agent_address_uses_it_only_for_mail_to_the_owner(world):
    run(world, "gws-side", "gmail", "+send", "--to", "owner@example.org", **session())
    assert "owner+agent@example.org" in called(world)
    run(world, "gws-side", "gmail", "+send", "--to", "merchant@shop.com", **session())
    assert "--from" not in called(world)
