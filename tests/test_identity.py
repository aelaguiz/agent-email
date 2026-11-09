import json

from agent_email import config, identity


def test_a_grant_named_for_the_agent_is_its_mailbox(home):
    assert identity.mailbox_for("growth-lead", str(home / "brain/pods/growth/lead"))[:2] == ("growth-lead", "growth-lead@example.com")


def test_everyone_else_uses_their_folders_default(home):
    assert identity.mailbox_for("cfo-specialist", str(home / "brain/specialists/cfo")) == ("chief", "chief@example.com", "owner@example.org")


def test_an_agent_whose_address_isnt_its_name_uses_the_mailbox_that_names_it(home):
    path = config.ROOT / "config.json"
    s = json.loads(path.read_text())
    s["mailboxes"]["money"] = {"address": "ledger@example.com", "agent_id": "cfo-specialist",
                               "folder": str(home / "brain/specialists/cfo")}
    path.write_text(json.dumps(s))
    (home / "grants" / "gws-money-credentials.json").write_text("{}")
    assert identity.mailbox_for("cfo-specialist", str(home / "brain"))[:2] == ("money", "ledger@example.com")
    assert identity.mailbox_for("money", str(home / "brain"))[:2] == ("money", "ledger@example.com")
    box = next(b for b in identity.mailboxes() if b["account"] == "money")
    assert identity.agent_from_address("ledger@example.com", box) == ("cfo-specialist", box["folder"])


def test_the_longest_folder_wins(home):
    assert identity.mailbox_for(None, str(home))[2] == "owner@gmail.com"
    assert identity.mailbox_for(None, str(home / "brain"))[2] == "owner@example.org"


def test_the_owners_own_account_is_never_an_agents_mailbox(home):
    assert identity.mailbox_for("fc", str(home / "brain"))[0] == "chief"


def test_an_owner_account_uses_its_agent_address(home):
    (home / "cj").mkdir()
    assert identity.mailbox_for(None, str(home / "cj")) == ("side", "owner+agent@example.net", "owner@example.net")


def test_every_agent_account_is_watched_and_the_owners_are_not(home):
    boxes = {b["account"]: b for b in identity.mailboxes()}
    assert set(boxes) == {"chief", "side", "growth-lead"}
    assert boxes["growth-lead"]["folder"].endswith("pods/growth/lead")
    assert boxes["side"]["own_mailbox"]


def test_a_plus_tag_names_an_agent(home):
    chief = next(b for b in identity.mailboxes() if b["account"] == "chief")
    assert identity.agent_from_address("chief+cfo-specialist@example.com", chief)[1].endswith("specialists/cfo")
    assert identity.agent_from_address("chief@example.com", chief)[0] == "chief"
    assert identity.agent_from_address("chief+nobody@example.com", chief) == ("nobody", chief["folder"])


def test_an_agent_without_a_mailbox_sends_from_its_folders_and_isnt_watched(home):
    path = config.ROOT / "config.json"
    s = json.loads(path.read_text())
    s["no_mailbox"] = ["growth-lead"]
    path.write_text(json.dumps(s))
    assert identity.mailbox_for("growth-lead", str(home / "brain/pods/growth/lead"))[:2] == ("chief", "chief@example.com")
    assert "growth-lead" not in {b["account"] for b in identity.mailboxes()}
    assert identity.agent_without_mailbox("Growth-Lead@example.com")[1].endswith("pods/growth/lead")
    assert identity.agent_without_mailbox("chief@example.com") is None
