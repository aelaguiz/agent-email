import pytest

import samples as s
from agent_email import sender


@pytest.mark.parametrize("headers", [s.DEFAULT_SENDER, s.PRIMARY_ADDRESS, s.GOOGLE_SIGNING_DOMAIN, s.PERSONAL_GMAIL])
def test_the_owners_real_mail_passes(headers):
    assert sender.check(headers, ["INBOX"], s.OWNERS).ok


@pytest.mark.parametrize("headers", [s.FORGED_THROUGH_GROUP, s.FORGED_NO_LIST_HEADERS, s.FORGED_FROM_A_SERVER,
                                     s.FAKE_VERDICT_BELOW, s.VACATION])
def test_mail_only_claiming_to_be_the_owner_fails(headers):
    v = sender.check(headers, ["INBOX"], s.OWNERS)
    assert not v.ok and v.claims_owner


def test_a_strangers_mail_is_not_a_claim_on_the_owner():
    v = sender.check(s.GROUP_MAIL, ["INBOX"], s.OWNERS)
    assert not v.ok and not v.claims_owner


def test_no_verdict_from_google_fails():
    assert not sender.check(s.h(From=s.WORK), ["INBOX"], s.OWNERS).ok


def test_two_from_addresses_fail():
    assert not sender.check(s.h(From=f"{s.WORK}, evil@badguy.net"), ["INBOX"], s.OWNERS).ok


def test_own_mailbox_needs_the_sent_label():
    assert sender.check(s.OWN_MAILBOX, ["SENT", "INBOX"], s.OWNERS, own_mailbox=True).ok
    assert not sender.check(s.OWN_MAILBOX, ["INBOX"], s.OWNERS, own_mailbox=True).ok


def test_a_signature_from_a_strangers_google_domain_fails():
    results = (f"mx.google.com; dkim=pass header.i=@badguy-net.20251104.gappssmtp.com; "
               f"spf=pass smtp.mailfrom={s.WORK}")
    assert not sender.check(s.h(Authentication_Results=results, From=s.WORK), [], s.OWNERS).ok
