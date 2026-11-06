"""Headers captured from real mail on November 6, 2026, with addresses, tokens and signatures replaced.
OWNER has three addresses here: work (with an alias) and personal. The company's domain is example.com, its alias
domain is example.org, and its Google signing domain is example-com.20251104.gappssmtp.com."""
WORK, ALIAS, PERSONAL = "owner@example.com", "owner@example.org", "owner@gmail.com"
OWNERS = [WORK, ALIAS, PERSONAL]


def h(**kw):
    return [{"name": k.replace("_", "-"), "value": v} for k, v in kw.items()]


GOOGLE_IP = "(google.com: domain of %s designates 209.85.220.41 as permitted sender)"

# The owner's reply from his default sender: an alias, sent from his main account.
DEFAULT_SENDER = h(Delivered_To="agent@example.com", Authentication_Results=(
    "mx.google.com;       dkim=pass header.i=@example.org header.s=google header.b=As3AZGOt;       arc=pass (i=1);"
    f"       spf=pass {GOOGLE_IP % WORK} smtp.mailfrom={WORK};"
    "       dmarc=pass (p=NONE sp=NONE dis=NONE) header.from=example.org;       dara=neutral header.i=@example.com"),
    From=f"Owner Name <{ALIAS}>", To="Agent <agent@example.com>")

PRIMARY_ADDRESS = h(Authentication_Results=(
    "mx.google.com;       dkim=pass header.i=@example.com header.s=google header.b=abcdefgh;       arc=pass (i=1);"
    f"       spf=pass {GOOGLE_IP % WORK} smtp.mailfrom={WORK};       dara=neutral header.i=@example.com"),
    From=f"Owner Name <{WORK}>", To="Agent <agent@example.com>")

# His real reply of October 17: signed by the domain Google gives a Workspace.
GOOGLE_SIGNING_DOMAIN = h(Authentication_Results=(
    "mx.google.com;       dkim=pass header.i=@example-com.20251104.gappssmtp.com header.s=20251104 header.b=eq8kV+C5;"
    f"       arc=pass (i=1);       spf=pass {GOOGLE_IP % WORK} smtp.mailfrom={WORK};"
    "       dara=neutral header.i=@example.com"),
    From=f"Owner Name <{WORK}>", To="Agent <agent@example.com>")

PERSONAL_GMAIL = h(Authentication_Results=(
    "mx.google.com;       dkim=pass header.i=@gmail.com header.s=20260707 header.b=zzzzzzzz;       arc=pass (i=1);"
    f"       spf=pass {GOOGLE_IP % PERSONAL} smtp.mailfrom={PERSONAL};"
    "       dmarc=pass (p=NONE sp=QUARANTINE dis=NONE) header.from=gmail.com"),
    From=f"Owner Name <{PERSONAL}>", To="Agent <agent@example.com>")

GROUP_RESULTS = (
    "mx.google.com;       dkim=pass header.i=@example.com header.s=google header.b=FfeyXiwN;"
    "       arc=pass (i=2 dkim=pass dkdomain=outsider-com.20260707.gappssmtp.com);"
    f"       spf=pass {GOOGLE_IP % 'support+bncabc@example.com'} smtp.mailfrom=support+bncABC@example.com")

# A stranger's real mail through the public support@ group: signed by our domain, with his From line kept.
GROUP_MAIL = h(Authentication_Results=GROUP_RESULTS, From="partners@outsider.com", To="support@example.org",
               List_ID="<support.example.com>", Mailing_list="list support@example.com", X_Google_Group_Id="344943117084")

# The same path with the owner's address forged. Group mail arrives this way when the From domain has no DMARC policy.
FORGED_THROUGH_GROUP = h(Authentication_Results=GROUP_RESULTS, From=f"Owner Name <{WORK}>", To="support@example.org",
                         List_ID="<support.example.com>", Mailing_list="list support@example.com",
                         X_Google_Group_Id="344943117084")

# Forged through the group, with the list headers somehow gone: the envelope still gives it away.
FORGED_NO_LIST_HEADERS = h(Authentication_Results=GROUP_RESULTS, From=f"Owner Name <{WORK}>")

FORGED_FROM_A_SERVER = h(Authentication_Results=(
    "mx.google.com;       dkim=pass header.i=@badguy.net header.s=s1 header.b=aaaa;"
    "       spf=pass (google.com: domain of bounce@badguy.net designates 1.2.3.4 as permitted sender) "
    "smtp.mailfrom=bounce@badguy.net"), From=f"Owner Name <{WORK}>")

# A stranger writes his own Authentication-Results; Google's real one sits above it.
FAKE_VERDICT_BELOW = [
    {"name": "Authentication-Results", "value": "mx.google.com;       spf=fail smtp.mailfrom=bounce@badguy.net"},
    {"name": "Authentication-Results", "value": (
        f"mx.google.com;       dkim=pass header.i=@example.com;       spf=pass smtp.mailfrom={WORK}")},
    {"name": "From", "value": WORK}]

VACATION = PRIMARY_ADDRESS + h(Auto_Submitted="auto-replied")

OWN_MAILBOX = h(From=f"Owner Name <{ALIAS}>", To=f"Agent <owner+agent@example.org>", Subject="Re: report")
