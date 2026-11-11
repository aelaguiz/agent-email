"""Every email an agent sends, in one shape that reads on a phone.

Plain text never goes out: Gmail re-wraps it at about 69 characters on the way, so on a phone every line breaks twice.
The agent writes light Markdown (or its own HTML) and this turns it into formatted HTML: an optional label saying what
kind of email it is, the body, and a sign-off with the sender's name, so the first line is free for the news.
"""
import html
import re

FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
P = "margin:0 0 12px"
LIST = "margin:0 0 12px;padding-left:22px"
LI = "margin:0 0 6px"
HEAD = "margin:18px 0 6px;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#5f6368"
BUTTON = ("display:inline-block;background:#1a73e8;color:#ffffff;text-decoration:none;border-radius:8px;"
          "padding:9px 14px;font-size:15px;font-weight:600;margin:0 8px 8px 0")
# A label's color comes from its first word, so "Problem · fixed tonight" is red and "Update · nothing needs you" blue.
COLORS = [(("problem", "broken", "incident", "outage"), "#c62828"), (("retro", "correction"), "#b45309"),
          (("needs", "decision", "ask", "approve", "your"), "#a16207"), (("update", "daily", "weekly", "status"), "#1d4ed8"),
          (("deck", "report"), "#6d28d9"), (("result", "read"), "#15803d")]

BULLET = re.compile(r"^\s*[-*•]\s+")
NUMBER = re.compile(r"^\s*\d+[.)]\s+")
LINK_ONLY = re.compile(r"^\s*\[([^\]]+)\]\((https?://[^)\s]+)\)\s*$")


def inline(text):
    """Escape, then **bold**, `code`, [label](url) and bare links."""
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    links = []

    def keep(m):
        links.append(f'<a href="{html.escape(m.group(2))}" style="color:#1a73e8">{m.group(1)}</a>')
        return f"\x00{len(links) - 1}\x00"
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", keep, t)
    t = re.sub(r"(?<![\"'>])(https?://[^\s<]+[^\s<.,;:)])", r'<a href="\1" style="color:#1a73e8">\1</a>', t)
    return re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], t)


def markdown(text):
    """Light Markdown to HTML. Lines inside a paragraph or a list item are joined, so text an agent wrapped by hand
    still flows on a phone."""
    out = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.split("\n")
        if len(lines) == 1 and lines[0].lstrip().startswith("#"):
            out.append(f'<p style="{HEAD}">{inline(lines[0].lstrip("# ").strip())}</p>')
            continue
        if all(LINK_ONLY.match(line) for line in lines):
            out.append('<p style="margin:14px 0 4px">' + "".join(
                f'<a href="{html.escape(m.group(2))}" style="{BUTTON}">{inline(m.group(1))}</a>'
                for m in (LINK_ONLY.match(line) for line in lines)) + "</p>")
            continue
        runs = []   # (kind, [items]); kind is "p", "ul" or "ol"
        for line in lines:
            if line.lstrip().startswith("#"):
                runs.append(("h", [line.lstrip("# ").strip()]))
                continue
            kind = "ul" if BULLET.match(line) else "ol" if NUMBER.match(line) else None
            if kind:
                item = NUMBER.sub("", BULLET.sub("", line, 1), 1) if kind == "ol" else BULLET.sub("", line, 1)
                if runs and runs[-1][0] == kind:
                    runs[-1][1].append(item)
                else:
                    runs.append((kind, [item]))
            elif runs and runs[-1][0] in ("ul", "ol") and line.startswith((" ", "\t")):
                runs[-1][1][-1] += " " + line.strip()      # a list item the agent wrapped onto the next line
            elif runs and runs[-1][0] == "p":
                runs[-1][1].append(line.strip())
            else:
                runs.append(("p", [line.strip()]))
        for kind, items in runs:
            if kind == "h":
                out.append(f'<p style="{HEAD}">{inline(items[0])}</p>')
            elif kind == "p":
                out.append(f'<p style="{P}">{inline(" ".join(items))}</p>')
            else:
                out.append(f'<{kind} style="{LIST}">' + "".join(f'<li style="{LI}">{inline(i.strip())}</li>' for i in items) + f"</{kind}>")
    return "\n".join(out)


def label_color(label):
    first = label.strip().split()[0].lower().strip("·:") if label.strip() else ""
    return next((c for words, c in COLORS if first in words), "#5b6070")


def email(body, is_html=False, label=None, signer=None):
    """The whole email as HTML: the label, the body, and the sign-off."""
    parts = []
    if label:
        parts.append(f'<p style="margin:0 0 12px"><span style="display:inline-block;background:{label_color(label)};color:#ffffff;'
                     f'font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;border-radius:5px;'
                     f'padding:3px 8px">{html.escape(label)}</span></p>')
    parts.append(body if is_html else markdown(body))
    if signer:
        parts.append(f'<p style="margin:18px 0 0;color:#5f6368;font-size:14px">{html.escape(signer)}</p>')
    return (f'<div style="font-family:{FONT};font-size:16px;line-height:1.5;color:#1f1f1f;max-width:640px">'
            + "\n".join(parts) + "</div>")


def subject(text):
    """One line: a subject with a line break or a tab in it shows a gap in his inbox."""
    return " ".join(text.split())
