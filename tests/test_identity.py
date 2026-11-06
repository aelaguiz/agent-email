from agent_email import config, identity


def test_a_grant_named_for_the_agent_is_its_mailbox(home):
    assert identity.mailbox_for("growth-lead", str(home / "brain/pods/growth/lead"))[:2] == ("growth-lead", "growth-lead@example.com")


def test_everyone_else_uses_their_folders_default(home):
    assert identity.mailbox_for("cfo-specialist", str(home / "brain/specialists/cfo")) == ("chief", "chief@example.com", "owner@example.org")


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
