"""Is this email really from the owner?

Sessions that act on these emails run with full permissions, so this check is the line between the owner and
everyone on the internet. A From line proves nothing, and neither does a passing signature from the owner's domain:
a Google Group re-signs a stranger's mail with that domain and keeps the stranger's From line. What a stranger can't
produce is Google's own record that the mail came straight from one of the owner's addresses. So the check reads
Google's verdict and asks for the exact envelope sender, a signature from the From address's own domain, and no sign
of a mailing list.
"""
import re
from dataclasses import dataclass
from email.utils import getaddresses

LIST_HEADERS = ("list-id", "mailing-list", "x-google-group-id")


@dataclass
class Verdict:
    ok: bool
    claims_owner: bool     # the From line names the owner, so a failure may be forgery or a real email we misjudged
    reason: str


def value(headers, name):
    """The topmost header of that name. Headers are newest first, so this is the last server's."""
    name = name.lower()
    return next((h["value"] for h in headers if h["name"].lower() == name), None)


def from_address(headers):
    """The From address, or None unless there is exactly one."""
    found = [a.lower() for _, a in getaddresses([value(headers, "from") or ""]) if a]
    return found[0] if len(found) == 1 else None


def google_verdict(headers):
    """Google's own Authentication-Results. It adds this above everything else on arrival, so a copy a sender wrote
    itself sits lower down and is never the first one."""
    results = value(headers, "authentication-results") or ""
    return results if results.lstrip().startswith("mx.google.com") else None


def _clauses(results):
    return [" ".join(c.split()) for c in results.split(";")]


def envelope_sender(results):
    for clause in _clauses(results):
        m = re.match(r"spf=pass\b.*\bsmtp\.mailfrom=(\S+)", clause)
        if m:
            return m.group(1).lower()
    return None


def signing_domains(results):
    """Domains with a passing DKIM signature."""
    out = []
    for clause in _clauses(results):
        m = re.match(r"dkim=pass\b.*?\bheader\.i=(\S+)", clause)
        if m:
            out.append(m.group(1).lower().rsplit("@", 1)[-1])
    return out


def _signed_by_owner(domains, sender_domain, owner_domains):
    """Signed by the From address's own domain, or by the Google signing domain of one of the owner's domains
    (example-com.20251104.gappssmtp.com for example.com), which Workspace uses when a domain has no key of its own."""
    tenants = {d.replace(".", "-") for d in owner_domains}
    for d in domains:
        if d == sender_domain:
            return True
        m = re.fullmatch(r"([a-z0-9-]+)\.\d+\.gappssmtp\.com", d)
        if m and m.group(1) in tenants:
            return True
    return False


def check(headers, labels, owner_addresses, own_mailbox=False):
    owners = {a.lower() for a in owner_addresses}
    sender = from_address(headers)
    if sender not in owners:
        return Verdict(False, False, "from someone else")
    no = lambda why: Verdict(False, True, why)

    auto = (value(headers, "auto-submitted") or "no").strip().lower()
    if auto != "no":
        return no("an automatic reply")
    if own_mailbox:
        # Mail between the owner's own addresses in one mailbox never leaves it, so Google writes no verdict.
        # Its proof is that this account sent it.
        return Verdict(True, True, "sent from the owner's own mailbox") if "SENT" in (labels or []) else no(
            "reached the owner's mailbox from outside it")
    if any(value(headers, h) for h in LIST_HEADERS):
        return no("came through a mailing list")
    results = google_verdict(headers)
    if not results:
        return no("has no verdict from Google")
    if envelope_sender(results) not in owners:
        return no("its envelope sender isn't one of the owner's addresses")
    owner_domains = {a.rsplit("@", 1)[-1] for a in owners}
    if not _signed_by_owner(signing_domains(results), sender.rsplit("@", 1)[-1], owner_domains):
        return no("isn't signed by the owner's domain")
    return Verdict(True, True, "verified")
