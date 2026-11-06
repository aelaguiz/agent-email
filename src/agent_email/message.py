"""Reading a Gmail message: the owner's own words, anything he forwarded, and his attachments."""
import base64
import html
import re

QUOTE_RE = re.compile(r"^On [^\n]{5,160}?(?:\n[^\n]{0,80}?){0,2}\bwrote:[ \t]*$", re.M)
FORWARD_RE = re.compile(r"^-{5,} ?Forwarded message ?-{5,}[ \t]*$", re.M | re.I)


def decode(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _parts(payload):
    yield payload
    for p in payload.get("parts") or []:
        yield from _parts(p)


def _to_text(markup):
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", markup)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6])>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def body_text(payload):
    """The plain text part, or the HTML part reduced to text when there is no plain one."""
    html_part = None
    for p in _parts(payload):
        data = (p.get("body") or {}).get("data")
        if not data or p.get("filename"):
            continue
        if p.get("mimeType") == "text/plain":
            return decode(data).decode("utf-8", "replace")
        if p.get("mimeType") == "text/html" and html_part is None:
            html_part = decode(data).decode("utf-8", "replace")
    return _to_text(html_part) if html_part else ""


def split_reply(text):
    """(his words, forwarded text). His words stop at the quote of the email he answered. Forwarded text is kept
    apart because it isn't his: he passed it on."""
    text = text.replace("\r\n", "\n")
    fwd = FORWARD_RE.search(text)
    forwarded = ""
    if fwd:
        forwarded = text[fwd.start():].strip()
        text = text[:fwd.start()]
    quote = QUOTE_RE.search(text)
    if quote:
        text = text[:quote.start()]
    return "\n".join(line for line in text.split("\n") if not line.startswith(">")).strip(), forwarded


def attachments(payload):
    """Files on the message: name, size, type and Gmail's attachment id."""
    out = []
    for p in _parts(payload):
        body = p.get("body") or {}
        if p.get("filename") and body.get("attachmentId"):
            out.append({"name": p["filename"], "size": body.get("size"), "type": p.get("mimeType"),
                        "id": body["attachmentId"]})
    return out


def safe_name(name, index):
    """A file name that stays inside the folder it's saved in; the name came from an email."""
    base = re.sub(r"[^\w.\- ]+", "_", name.replace("\\", "/").rsplit("/", 1)[-1]).strip(". ")
    return base or f"attachment-{index}"
