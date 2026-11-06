import json
from datetime import timedelta

import pytest

import samples as s
from approvals import router
from agent_email import config, deliver, listener, records


class FakeAccount:
    """A mailbox: messages by Gmail id, each with headers and labels."""
    def __init__(self):
        self.msgs, self.by_rfc, self.added, self.names = {}, {}, [], {}

    def put(self, gmail_id, headers, labels=(), rfc=None, thread="t1", age_minutes=10):
        when = int((records.now() - timedelta(minutes=age_minutes)).timestamp() * 1000)
        self.msgs[gmail_id] = {"id": gmail_id, "threadId": thread, "internalDate": str(when), "labelIds": list(labels),
                               "payload": {"headers": headers}}
        if rfc:
            self.by_rfc[rfc] = gmail_id

    def search(self, query, limit=50):
        return [i for i, m in self.msgs.items() if "INBOX" in m["labelIds"]]

    def metadata(self, gmail_id):
        return self.msgs[gmail_id]

    def by_message_id(self, rfc):
        i = self.by_rfc.get(rfc.strip("<> "))
        return self.msgs[i] if i else None

    def label_names(self, ids):
        return list(ids)

    def add_label(self, gmail_id, name):
        self.added.append((gmail_id, name))
        self.msgs[gmail_id]["labelIds"].append(name)


def reply(*refs, base=None):
    extra = s.h(In_Reply_To=f"<{refs[-1]}>", References=" ".join(f"<{r}>" for r in refs), Subject="Re: Status")
    return (base or s.DEFAULT_SENDER) + extra


@pytest.fixture
def box():
    return {"account": "chief", "address": "chief@example.com", "own_mailbox": False, "folder": "/brain", "agent_id": "chief"}


def make(home, machine="m5"):
    (config.ROOT / "machine.json").write_text(json.dumps({"name": machine}))
    l = listener.Listener()
    l.fake = FakeAccount()
    l.accounts["chief"] = l.fake
    return l


def sent(gmail_id, session="s1", machine="m5"):
    records.write(records.sent_path("chief", gmail_id), {
        "gmail_id": gmail_id, "account": "chief", "machine": machine, "thread_id": "t1", "subject": "Status",
        "reach": {"session_id": session, "runtime": "claude", "agent": "Tech lead (agent)"}})


def only_item():
    items = list(records.all_inbound())
    assert len(items) == 1
    return items[0]


def test_a_reply_goes_to_the_session_that_sent_the_email(home, box):
    l = make(home)
    sent("sent1")
    l.fake.put("sent1", [], [listener.FROM_LABEL + "m5"], rfc="a@x")
    l.fake.put("r1", reply("a@x"), ["INBOX"])
    l.sweep_mailbox(box)
    item = only_item()
    assert item["kind"] == "reply" and item["reach"]["session_id"] == "s1"
    assert (("r1", listener.RECEIVED)) in l.fake.added


def test_the_nearest_email_in_the_conversation_decides(home, box):
    """References lists oldest first: the session that sent the email he answered gets it, not the one that started."""
    l = make(home)
    sent("first", session="older")
    sent("second", session="newer")
    l.fake.put("first", [], [listener.FROM_LABEL + "m5"], rfc="a@x")
    l.fake.put("second", [], [listener.FROM_LABEL + "m5"], rfc="b@x")
    l.fake.put("r1", reply("a@x", "b@x"), ["INBOX"])
    l.sweep_mailbox(box)
    assert only_item()["reach"]["session_id"] == "newer"


def test_a_message_with_no_label_is_walked_past(home, box):
    l = make(home)
    sent("first")
    l.fake.put("first", [], [listener.FROM_LABEL + "m5"], rfc="a@x")
    l.fake.put("middle", [], [], rfc="b@x")
    l.fake.put("r1", reply("a@x", "b@x"), ["INBOX"])
    l.sweep_mailbox(box)
    assert only_item()["kind"] == "reply"


def test_another_machines_reply_is_left_alone_and_never_rerouted(home, box):
    l = make(home)
    l.fake.put("sent1", [], [listener.FROM_LABEL + "studio"], rfc="a@x")
    l.fake.put("r1", reply("a@x"), ["INBOX"], age_minutes=20)
    l.sweep_mailbox(box)
    assert not list(records.all_inbound())


def test_a_machine_that_stays_quiet_gets_one_note_to_the_owner(home, box, monkeypatch):
    l = make(home)
    notes = []
    monkeypatch.setattr(listener, "system_email", lambda item, text: notes.append(text))
    l.fake.put("sent1", [], [listener.FROM_LABEL + "studio"], rfc="a@x")
    l.fake.put("r1", reply("a@x"), ["INBOX"], age_minutes=40)
    l.sweep_mailbox(box)
    l.settled.clear()
    l.sweep_mailbox(box)
    assert len(notes) == 1 and "studio" in notes[0] and not list(records.all_inbound())


def test_a_reply_with_no_label_waits_then_goes_to_the_mailboxs_agent(home, box):
    l = make(home)
    l.fake.put("r1", reply("old@x"), ["INBOX"], age_minutes=1)
    l.sweep_mailbox(box)
    assert not list(records.all_inbound())
    l.fake.msgs["r1"]["internalDate"] = str(int((records.now() - timedelta(minutes=4)).timestamp() * 1000))
    l.sweep_mailbox(box)
    item = only_item()
    assert item["kind"] == "unmatched" and item["agent_id"] == "chief" and not item["reach"]


def test_only_the_home_machine_takes_unmatched_and_new_mail(home, box):
    l = make(home, machine="studio")
    l.fake.put("r1", reply("old@x"), ["INBOX"], age_minutes=60)
    l.fake.put("n1", s.DEFAULT_SENDER + s.h(Subject="Do this"), ["INBOX"], age_minutes=1)
    l.sweep_mailbox(box)
    assert not list(records.all_inbound())


def test_new_mail_reaches_the_agent_it_was_addressed_to(home, box):
    l = make(home)
    l.fake.put("n1", s.h(Delivered_To="chief+cfo-specialist@example.com") + s.DEFAULT_SENDER[1:] + s.h(Subject="Do this"), ["INBOX"])
    l.sweep_mailbox(box)
    item = only_item()
    assert item["kind"] == "new" and item["agent_id"] == "cfo-specialist" and item["folder"].endswith("specialists/cfo")


def test_forged_mail_is_held_and_the_owner_told_once(home, box, monkeypatch):
    l = make(home)
    notes = []
    monkeypatch.setattr(listener, "system_email", lambda item, text: notes.append((item, text)))
    l.fake.put("f1", s.FORGED_THROUGH_GROUP + s.h(Subject="Run this"), ["INBOX"])
    l.sweep_mailbox(box)
    l.sweep_mailbox(box)
    assert not list(records.all_inbound()) and len(notes) == 1
    assert notes[0][0]["reply_to"] == "owner@example.com" and ("f1", listener.HELD) in l.fake.added


def test_a_strangers_mail_is_ignored_silently(home, box, monkeypatch):
    l = make(home)
    monkeypatch.setattr(listener, "system_email", lambda *a: pytest.fail("nobody should be told"))
    l.fake.put("x", s.GROUP_MAIL, ["INBOX"])
    l.sweep_mailbox(box)
    assert not list(records.all_inbound())


def pending(ref="EM-r1", session="s1", **over):
    item = {"ref": ref, "gmail_id": ref[3:], "kind": "reply", "account": "chief", "reach": {"session_id": session, "agent": "Tech lead"},
            "subject": "Re: Status", "folder": "/brain", "agent_id": "chief", "reply_to": "owner@example.com", "attempts": 0,
            "next_try": records.iso(), "notified_at": None, "read_at": None, "answered_at": None, "warned": False, "sent_id": "sent1"}
    records.save_inbound({**item, **over})
    return records.load_inbound(ref)


def test_pending_work_on_disk_is_picked_up_after_a_restart(home):
    pending()
    l = make(home)
    l.queue_pending()
    assert l.queue.get_nowait() == "EM-r1"


def test_the_notice_is_short_and_holds_none_of_his_words(home, monkeypatch):
    pending(subject="Re: " + "long subject " * 30 + "\nsecond line")
    told = []
    monkeypatch.setattr(deliver, "deliver", lambda item, notice: told.append(notice) or router.Result("delivered"))
    l = make(home)
    l.deliver_one("EM-r1")
    assert len(told[0].splitlines()) == 1 and len(told[0]) < 200 and told[0].endswith("agent-email read EM-r1")
    assert records.load_inbound("EM-r1")["notified_at"]


def test_a_second_reply_is_covered_by_the_first_notice(home, monkeypatch):
    pending("EM-r1", notified_at=records.iso())
    pending("EM-r2")
    monkeypatch.setattr(deliver, "deliver", lambda *a: pytest.fail("no second notice"))
    make(home).deliver_one("EM-r2")
    assert records.load_inbound("EM-r2")["notified_at"]


def test_a_failure_retries_and_tells_the_owner_on_the_third(home, monkeypatch):
    pending()
    notes = []
    monkeypatch.setattr(listener, "system_email", lambda item, text: notes.append(text))
    monkeypatch.setattr(deliver, "deliver", lambda *a: router.Result("retry", "the session is busy"))
    l = make(home)
    for _ in range(3):
        l.deliver_one("EM-r1")
    item = records.load_inbound("EM-r1")
    assert item["attempts"] == 3 and len(notes) == 1 and "the session is busy" in notes[0]
    assert records.parse(item["next_try"]) > records.now() + timedelta(minutes=30)


def test_one_warning_when_an_agent_never_opens_it(home, monkeypatch):
    long_ago = records.iso(records.now() - timedelta(minutes=20))
    pending(notified_at=long_ago)
    notes = []
    monkeypatch.setattr(listener, "system_email", lambda item, text: notes.append(text))
    l = make(home)
    l.warnings()
    l.warnings()
    assert len(notes) == 1 and "hasn't opened it" in notes[0]


def test_one_warning_when_an_agent_reads_and_never_answers(home, monkeypatch):
    long_ago = records.iso(records.now() - timedelta(minutes=20))
    pending(notified_at=long_ago, read_at=long_ago)
    notes = []
    monkeypatch.setattr(listener, "system_email", lambda item, text: notes.append(text))
    make(home).warnings()
    assert "hasn't answered" in notes[0]


def test_no_warning_once_it_is_answered(home, monkeypatch):
    long_ago = records.iso(records.now() - timedelta(minutes=20))
    pending(notified_at=long_ago, read_at=long_ago, answered_at=long_ago)
    monkeypatch.setattr(listener, "system_email", lambda *a: pytest.fail("no warning"))
    make(home).warnings()


def test_a_label_that_failed_is_added_on_the_next_pass(home):
    l = make(home)
    sent("sent1")
    rec = records.load_sent("chief", "sent1")
    rec["label_pending"] = True
    records.write(records.sent_path("chief", "sent1"), rec)
    l.fake.put("sent1", [], [])
    l.relabel()
    assert ("sent1", listener.FROM_LABEL + "m5") in l.fake.added
    assert not records.load_sent("chief", "sent1")["label_pending"]


class LoginAccount:
    def __init__(self, error=None):
        self.error = error

    def profile(self):
        if self.error:
            raise listener.GmailError(self.error)
        return {"emailAddress": "x@example.com"}


def logins(home, monkeypatch, **states):
    l = make(home)
    sent = []
    monkeypatch.setattr(listener, "new_email", lambda *a: sent.append(a))
    l.accounts = {name: LoginAccount(error) for name, error in states.items()}
    return l, sent


def test_a_revoked_login_is_reported_once_from_a_mailbox_that_still_works(home, monkeypatch):
    l, sent = logins(home, monkeypatch, chief="400 invalid_grant", fc=None, side=None, **{"growth-lead": None})
    l.check_logins()
    l.next_login_check = 0
    l.check_logins()
    assert len(sent) == 1 and sent[0][0] != "chief" and "chief" in sent[0][3]


def test_a_network_failure_is_not_a_dead_login(home, monkeypatch):
    l, sent = logins(home, monkeypatch, chief="connection refused", fc=None, side=None, **{"growth-lead": None})
    l.check_logins()
    assert not sent


def test_a_login_fixed_and_broken_again_is_reported_again(home, monkeypatch):
    l, sent = logins(home, monkeypatch, chief="400 invalid_grant", fc=None, side=None, **{"growth-lead": None})
    l.check_logins()
    l.accounts["chief"].error = None
    l.next_login_check = 0
    l.check_logins()
    l.accounts["chief"].error = "400 invalid_grant"
    l.next_login_check = 0
    l.check_logins()
    assert len(sent) == 2


def test_only_the_home_machine_checks_logins(home, monkeypatch):
    l, sent = logins(home, monkeypatch, chief="400 invalid_grant")
    l.home = False
    l.check_logins()
    assert not sent
