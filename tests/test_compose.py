from types import SimpleNamespace

from agent_email import cli, compose


def test_text_wrapped_by_hand_flows_again_and_lists_become_lists():
    text = ("Three bugs got past QA. Two reached players: one is fixed\ntonight, and one is still open.\n\n"
            "What players hit:\n- A pot froze for 7.4 seconds\n  when a player sat out.\n- Resume fails on a slow connection.\n\n"
            "Your calls:\n1. Pause both reports?\n2. Is that the right level?")
    out = compose.markdown(text)
    assert "fixed tonight, and one" in out                      # the hand-made line break is gone
    assert "<p" in out and "<ul" in out and "<ol" in out
    assert "A pot froze for 7.4 seconds when a player sat out." in out
    assert out.index("What players hit:") < out.index("<ul")


def test_bold_links_and_a_line_of_links_become_buttons():
    out = compose.markdown("**Fixed since 5:18 am.** See [the record](https://example.com/r).\n\n"
                           "[Open the deck](https://example.com/d)\n[The grid](https://example.com/g)")
    assert "<b>Fixed since 5:18 am.</b>" in out and 'href="https://example.com/r"' in out
    assert out.count("display:inline-block") == 2               # the two links on their own lines are buttons


def test_a_heading_is_a_small_label_and_text_is_escaped():
    out = compose.markdown("## Why QA missed them\n\nIt saw <script> & tags.")
    assert "text-transform:uppercase" in out and "Why QA missed them" in out
    assert "&lt;script&gt; &amp; tags" in out
    tight = compose.markdown("## How it happened\nThe book says to read it back.\n## What changes\n- One thing.")
    assert "##" not in tight and tight.count("text-transform:uppercase") == 2 and "<li" in tight


def test_the_email_has_its_label_and_sign_off_and_keeps_html_it_is_given():
    out = compose.email("<p>Hello</p>", is_html=True, label="Problem · fixed tonight", signer="Core dev pod lead (agent)")
    assert "<p>Hello</p>" in out and "Problem · fixed tonight" in out and "#c62828" in out
    assert out.rstrip().endswith("</div>") and "Core dev pod lead (agent)" in out
    assert compose.label_color("Update · nothing needs you") == "#1d4ed8"
    assert compose.label_color("Whatever") == "#5b6070"


def test_every_send_goes_as_html_with_a_one_line_subject(monkeypatch):
    sent = {}
    monkeypatch.setattr(cli.config, "settings", lambda: {})
    monkeypatch.setattr(cli.identity, "session", lambda: {"agent_id": "growth-lead", "cwd": "/x", "agent": "Growth pod lead"})
    monkeypatch.setattr(cli.identity, "mailbox_for", lambda *a: ("chief", "chief@example.com", "owner@example.com"))
    monkeypatch.setattr(cli.subprocess, "run", lambda args, **k: sent.setdefault("args", args) and SimpleNamespace(returncode=0))
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    a = SimpleNamespace(subject="Team deck ready:\n\t51 things shipped", to=None, cc=None, attach=None,
                        body="The deck is ready.", body_file=None, html=False, label="Deck · ready to show")
    try:
        cli.cmd_send(a)
    except SystemExit:
        pass
    args = sent["args"]
    assert "--html" in args and args[args.index("--subject") + 1] == "Team deck ready: 51 things shipped"
    body = args[args.index("--body") + 1]
    assert "<p" in body and "Deck · ready to show" in body and "Growth pod lead" in body
