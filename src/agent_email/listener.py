"""`agent-email listen`: watch the mailboxes, work out which machine owns each email from the owner, and tell the right
session to read it.

Each machine runs one of these and Gmail is all they share. A reply belongs to the machine named by the label on the
email it answers, so every listener reaches the same answer and only one acts. Whatever this machine owns goes on disk
before anything else happens, so a restart picks up where it stopped.
"""
import logging
import logging.handlers
import queue
import threading
from email.utils import getaddresses
from datetime import datetime, timezone

from . import config, deliver, identity, records, sender
from .google import Account, GmailError

log = logging.getLogger("agent-email")

FROM_LABEL = "agent-email/from-"
RECEIVED, READ, HELD, NOTED = "agent-email/received", "agent-email/read", "agent-email/held", "agent-email/noted"
FAILURE_NOTE_AFTER = 3


def search_query(mailbox, s):
    owners = " OR ".join(s["owner_addresses"])
    start = int(datetime.fromisoformat(s["start_time"]).timestamp())
    q = f"in:inbox from:({owners}) -label:agent-email-read -label:agent-email-held after:{start}"
    return q + f" to:{mailbox['address']}" if mailbox["own_mailbox"] else q


def message_ids(headers):
    """The conversation, nearest first: the email he answered, then References from its end, which lists oldest first."""
    ids = []
    for token in [sender.value(headers, "in-reply-to") or ""] + list(reversed((sender.value(headers, "references") or "").split())):
        for one in token.split():
            if one not in ids:
                ids.append(one)
    return ids


def find_owner(account, headers):
    """(machine, Gmail id of the email he answered), or (None, None) if nothing in the conversation has a machine label."""
    for rfc_id in message_ids(headers):
        parent = account.by_message_id(rfc_id)
        if not parent:
            continue
        for name in account.label_names(parent.get("labelIds", [])):
            if name.startswith(FROM_LABEL):
                return name[len(FROM_LABEL):], parent["id"]
    return None, None


def age_minutes(msg):
    sent = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, timezone.utc)
    return (records.now() - sent).total_seconds() / 60


def clean_subject(subject):
    return " ".join((subject or "(no subject)").split())[:80]


def notice_for(item, s):
    owner, subject, ref = s["owner"], clean_subject(item.get("subject")), item["ref"]
    if item["kind"] == "new":
        return f'[Email] {owner} wrote to you about "{subject}". Read it: agent-email read {ref}'
    if item["kind"] == "unmatched":
        return (f'[Email] {owner} replied to "{subject}", an email this session did not send. '
                f"Read it and the conversation: agent-email read {ref} --full")
    return f'[Email] {owner} replied to "{subject}". Read it: agent-email read {ref}'


def system_email(item, text):
    """A note to the owner in the thread, from the same mailbox. Run through gws so it looks like any other email."""
    import os
    import subprocess
    s = config.settings()
    env = {**os.environ, "AGENT_EMAIL_SYSTEM": "1"}
    subprocess.run([os.path.expanduser(f"~/.local/bin/gws-{item['account']}"), "gmail", "+reply", "--message-id", item["gmail_id"],
                    "--to", item["reply_to"], "--body", text], env=env, capture_output=True, timeout=60, check=True)


class Listener:
    def __init__(self):
        self.s = config.settings()
        self.me = config.machine()["name"]
        self.home = self.s["home_machine"] == self.me
        self.accounts = {}
        self.boxes = identity.mailboxes(self.s)
        self.settled = set()         # emails this process has nothing more to do with
        self.queue = queue.Queue()
        self.queued = set()
        self.stop = threading.Event()

    def account(self, name):
        if name not in self.accounts:
            self.accounts[name] = Account(name, self.s)
        return self.accounts[name]

    def watched(self):
        if self.home:
            return self.boxes
        mine = {r["account"] for r in records.all_sent()}
        return [b for b in self.boxes if b["account"] in mine]

    # ----- finding mail -----

    def sweep(self):
        for box in self.watched():
            try:
                self.sweep_mailbox(box)
            except GmailError as e:
                log.warning("%s: %s", box["address"], e)
        self.relabel()
        self.queue_pending()
        self.warnings()

    def sweep_mailbox(self, box):
        account = self.account(box["account"])
        for gmail_id in account.search(search_query(box, self.s)):
            if gmail_id not in self.settled and not records.load_inbound(records.ref_for(gmail_id)):
                self.consider(box, account, gmail_id)

    def consider(self, box, account, gmail_id):
        msg = account.metadata(gmail_id)
        headers = msg["payload"]["headers"]
        verdict = sender.check(headers, msg.get("labelIds"), self.s["owner_addresses"], box["own_mailbox"])
        if not verdict.ok:
            log.info("%s %s: not counted, %s", box["address"], gmail_id, verdict.reason)
            self.settled.add(gmail_id)
            if verdict.claims_owner and self.home:
                self.hold(box, account, msg, verdict)
            return
        refs = message_ids(headers)
        if not refs:
            if self.home:
                self.take(box, msg, "new", parent=None)
            else:
                self.settled.add(gmail_id)
            return
        owner, parent = find_owner(account, headers)
        if owner == self.me:
            self.take(box, msg, "reply", parent=parent)
        elif owner is None:
            if self.home and age_minutes(msg) >= self.s["unlabeled_wait_minutes"]:
                self.take(box, msg, "unmatched", parent=None)
        elif self.home:
            self.check_waiting(box, account, msg, owner)
        else:
            self.settled.add(gmail_id)

    def hold(self, box, account, msg, verdict):
        """An email claiming to be the owner that failed the check. He hears once, at his real address, so a real email
        of his that we misjudged can't vanish in silence."""
        subject = sender.value(msg["payload"]["headers"], "subject")
        log.warning("%s %s: held back: %s", box["address"], msg["id"], verdict.reason)
        try:
            account.add_label(msg["id"], HELD)
            item = {"account": box["account"], "gmail_id": msg["id"], "reply_to": self.s["owner_addresses"][0]}
            system_email(item, f'An email claiming to be from you, "{clean_subject(subject)}", {verdict.reason}, so no agent '
                               f"was given it. If it was really you, write again from your usual address.")
        except Exception:
            log.exception("couldn't send the held-back note")

    def check_waiting(self, box, account, msg, owner):
        """A reply another machine owns. If that machine hasn't picked it up, the owner should hear why it's waiting."""
        if age_minutes(msg) < self.s["machine_off_minutes"]:
            return
        names = account.label_names(msg.get("labelIds", []))
        if RECEIVED in names or NOTED in names:
            self.settled.add(msg["id"])
            return
        headers = msg["payload"]["headers"]
        try:
            account.add_label(msg["id"], NOTED)
            item = {"account": box["account"], "gmail_id": msg["id"], "reply_to": sender.from_address(headers)}
            system_email(item, f"Your reply is waiting because the {owner} machine isn't picking up its mail. "
                               f"It will reach the agent when that machine is back.")
        except Exception:
            log.exception("couldn't send the waiting note")
        self.settled.add(msg["id"])

    def take(self, box, msg, kind, parent):
        headers = msg["payload"]["headers"]
        ref = records.ref_for(msg["id"])
        delivered_to = sender.value(headers, "delivered-to") or box["address"]
        agent_id, folder = identity.agent_from_address(delivered_to, box, self.s)
        sent = records.load_sent(box["account"], parent) if parent else None
        item = {
            "ref": ref, "gmail_id": msg["id"], "thread_id": msg["threadId"], "kind": kind,
            "account": box["account"], "mailbox": box["address"], "subject": sender.value(headers, "subject"),
            "reply_to": sender.from_address(headers), "agent_id": agent_id, "folder": folder,
            "sent_id": parent, "reach": (sent or {}).get("reach"), "received_at": records.iso(),
            "attempts": 0, "next_try": records.iso(), "notified_at": None, "read_at": None, "answered_at": None,
            "warned": False,
        }
        if kind == "reply" and not sent:
            item["kind"] = "unmatched"
        records.save_inbound(item)
        log.info("%s: %s for %s", ref, item["kind"], agent_id)
        try:
            self.account(box["account"]).add_label(msg["id"], RECEIVED)
        except GmailError as e:
            log.warning("%s: couldn't label it: %s", ref, e)

    # ----- telling the session -----

    def queue_pending(self):
        now = records.now()
        for item in records.all_inbound():
            if item["notified_at"] or item["read_at"] or item["ref"] in self.queued:
                continue
            if records.parse(item["next_try"]) <= now:
                self.queued.add(item["ref"])
                self.queue.put(item["ref"])

    def already_told(self, item):
        """True when this session has an unread email it was already told about: one read shows both."""
        sid = (item.get("reach") or {}).get("session_id")
        if not sid:
            return False
        return any(o["ref"] != item["ref"] and o["notified_at"] and not o["read_at"]
                   and (o.get("reach") or {}).get("session_id") == sid for o in records.all_inbound())

    def worker(self):
        while not self.stop.is_set():
            try:
                ref = self.queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.deliver_one(ref)
            except Exception as e:
                log.exception("%s: delivery failed", ref)
                self.after_failure(ref, f"delivery failed: {e}")
            finally:
                self.queued.discard(ref)

    def deliver_one(self, ref):
        item = records.load_inbound(ref)
        if item["notified_at"]:
            return
        if self.already_told(item):
            records.update_inbound(ref, notified_at=records.iso())
            log.info("%s: covered by an earlier notice", ref)
            return
        result = deliver.deliver(item, notice_for(item, self.s))
        log.info("%s: %s (%s)", ref, result.status, result.reason)
        if result.status == "delivered":
            changes = {"notified_at": records.iso()}
            if result.reach:
                changes["reach"] = {**records.load_inbound(ref).get("reach", {}), **result.reach}
            records.update_inbound(ref, **changes)
        else:
            self.after_failure(ref, result.reason)

    def after_failure(self, ref, reason):
        from datetime import timedelta
        item = records.load_inbound(ref)
        attempts = item["attempts"] + 1
        minutes = 5 if attempts < FAILURE_NOTE_AFTER else 60
        records.update_inbound(ref, attempts=attempts, last_error=reason,
                               next_try=records.iso(records.now() + timedelta(minutes=minutes)))
        if attempts == FAILURE_NOTE_AFTER:
            self.note(item, f"Your reply hasn't reached {self.who(item)} yet: {reason}. Still trying hourly.")

    @staticmethod
    def who(item):
        return (item.get("reach") or {}).get("agent") or item.get("agent_id") or "the agent"

    def note(self, item, text):
        try:
            system_email(item, text)
        except Exception:
            log.exception("%s: couldn't send a note", item["ref"])

    # ----- keeping the owner informed -----

    def warnings(self):
        limit = self.s["warn_minutes"]
        for item in records.all_inbound():
            if item["warned"] or item["answered_at"] or not item["notified_at"]:
                continue
            if not item["read_at"] and records.minutes_since(item["notified_at"]) >= limit:
                text = f"Your email reached {self.who(item)} {limit} minutes ago, but it hasn't opened it yet."
            elif item["read_at"] and records.minutes_since(item["read_at"]) >= limit:
                text = f"{self.who(item)} read your email {limit} minutes ago but hasn't answered yet."
            else:
                continue
            records.update_inbound(item["ref"], warned=True)
            self.note(item, text)

    def relabel(self):
        """Machine labels that failed when the email was sent."""
        for rec in records.all_sent():
            if rec.get("label_pending"):
                try:
                    self.account(rec["account"]).add_label(rec["gmail_id"], FROM_LABEL + self.me)
                    rec["label_pending"] = False
                    records.write(records.sent_path(rec["account"], rec["gmail_id"]), rec)
                except GmailError as e:
                    log.warning("%s: label still failing: %s", rec["gmail_id"], e)

    # ----- run -----

    def loop(self):
        while not self.stop.is_set():
            try:
                self.sweep()
            except Exception:
                log.exception("sweep failed")
            self.stop.wait(self.s["poll_seconds"])

    def run(self):
        log.info("listening on %s: %d mailboxes", self.me, len(self.watched()))
        threading.Thread(target=self.worker, daemon=True).start()
        self.loop()


def main():
    config.LOGS.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(config.LOGS / "listener.log", maxBytes=5_000_000, backupCount=3)
    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()],
                        format="%(asctime)s %(levelname)s %(message)s")
    Listener().run()
