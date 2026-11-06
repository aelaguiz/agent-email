# AGENTS.md

agent-email lets Amir talk to his coding agents by email. A reply to an agent's email tells the session that sent it to read the reply, on whichever of his machines it runs, and a new email to an agent's address reaches that agent. It also holds the one command every agent uses for Google. [README.md](README.md) covers install and use, and [docs/design.md](docs/design.md) covers how it works.

`CLAUDE.md` is a link to this file, not a second rulebook. This file is a few intuitions about working here; a new lesson deepens the one it belongs to.

## What matters here

**Email reaches sessions running with full permissions.** Anyone who gets past the sender check can give orders on Amir's machines, so that check is the line between him and everyone on the internet. A From line proves nothing, and "signed by our domain" proves little, because a Google Group re-signs mail from strangers. Read `src/agent_email/sender.py` and its header samples before touching it, and when a real email from Amir fails it, make the check understand that email. Never loosen it to let the case through.

**A reply Amir sent must reach someone, once, or he must hear that it didn't.** He writes from his phone and moves on, and he takes silence as handled. Each reply has one owner machine, the pending work is on disk before anything else happens, and restarts pick up where they stopped. Before changing any of that, ask what happens if the process dies on the next line.

**Every agent's Google access runs through `bin/gws-account`.** A bug there stops all of them at once, for Drive and Sheets as well as mail. So nothing email-related may ever fail or slow a Google call: the send has happened before any record is written, and everything after it is best effort. That script stays small, uses only the standard library, and runs on the older Python that ships with macOS.

**Never type an email's text into a session.** The input box gets one short fixed notice, and the agent reads the email itself with `agent-email read`. Long text and odd characters are fragile in an input box, and attachments can't go there at all.

**Teach intuitions, not rules.** [skills/agent-email/](skills/agent-email/) is what agents read to use this, and the notices it answers are model-facing prompts too. Say how to think about the thing and why, with a few varied cases, and trust the agent with the next one. Edit it with `$skill-authoring`, `$prompt-authoring` and `$intuition-building`, keep `agents/openai.yaml` in line with `SKILL.md`, and never write tests that check the skill's wording.

## How to build here

This is an internal tool for one person and his agents. Build the simplest thing that does the job, and weigh every guard by what it costs when it fires against how likely the failure really is. When you feel the pull to add a wait, a retry layer, a fallback, a flag or a mode, ask what real failure it prevents. Fail loud when something required is missing, except in the send path above.

Reuse approvals' delivery code by importing it. A bug in finding or resuming a session gets fixed in [agent-approvals](https://github.com/aelaguiz/agent-approvals), where both benefit, never worked around here.

Match the surrounding code: its naming, comment density and idiom. Comments explain non-obvious intent, never syntax.

## Commands

```bash
make test                     # unit tests, no network, no real mail
make install                  # install the command, skill, links and service on this machine
make verify_install           # check all of it
agent-email doctor            # this machine's setup and logins
agent-email accounts --fleet  # every account, on every machine
scripts/rollout.sh            # install on the other machines
```

Python runs through uv, 3.12 or newer, apart from `bin/gws-account`. The running service, skill and links are copies, so a change does nothing live until `make install`, and `scripts/rollout.sh` for the other machines. The live scenarios are in [docs/testing.md](docs/testing.md).

## Done means

"Works" means a real reply reached a real session and the agent acted on it. Unit tests alone don't prove the live path.

- `make test` passes. Add a test only for behavior that could really break. Tests use fakes for Gmail, Herdr and AI Manager, and real header samples with addresses changed.
- A change to delivery, routing, the listener or the sender check is seen working live.
- [README.md](README.md), [docs/design.md](docs/design.md) and [docs/testing.md](docs/testing.md) still describe what the code does.
- The change is committed and pushed to `main`. A task that delivers a change here already authorizes that.

## Red lines

- **This repo is public.** Never commit real addresses, staff names, session ids, token paths, machine names or tokens. Real config and internal plans go in `private/`, which git ignores, or in Amir's secrets repo. Read the diff before pushing.
- **Never print a token or grant.** Code reads grant files; nothing shows their contents.
- **These are real mailboxes.** Test mail goes only to Amir and the agent mailboxes, says TEST in its subject, and gets archived afterward. Never read Amir's own mail beyond what a task needs, and never email anyone else.
- **Git:** stage exact paths. Ask before a force push, a history rewrite or discarding work. Leave changes you didn't make alone.
- **Shared machines:** close the Herdr panes and sessions you start for live tests. Other agents' sessions are never yours to type into, restart or test against.

## Replies

Write in plain English, answer first, in Amir's terms for his product: "your reply reached the agent 30 seconds later", not "item delivered". No em dashes. Say what you didn't verify plainly.
