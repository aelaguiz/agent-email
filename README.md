# agent-email

Talk to your AI coding agents by email. Reply to any email an agent sent you and the session that sent it is told to read your reply, on whichever machine it runs, whether that session is open or closed. Email an agent's address and that agent picks it up. The agent answers in the same Gmail thread, to everyone your email went to, so you can hold a conversation from your phone.

```
agent ── gws-chief gmail +send ──▶ the one Google command ──▶ Gmail ──▶ you
                                     └─ records which session sent it

you reply in Gmail ──▶ the agent's mailbox ──▶ listener: is it really you? which email did you answer?
                                                 │
agent session ◀── "[Email] Sam replied to ... Read it: agent-email read EM-..." ◀──┘  (resumed first if it closed)
      │
      └── agent-email read ──▶ your full email and attachments
      └── agent-email reply ──▶ the same thread ──▶ you, and anyone else your email went to
```

- **Agents keep sending the way they already do.** Every Google command goes through one script, which notes which session sent each email. Agents don't have to change a thing, and `agent-email send` is there for new work.
- **Only a short notice goes in the agent's input box.** The agent reads your email itself, so long emails and attachments just work, and the system knows the agent actually opened it.
- **It knows it's you.** Sessions run with full permissions, so an email counts only if Google's own records show it came straight from one of your addresses. See [How we know it's you](docs/design.md#how-we-know-its-you).
- **A reply is never lost in silence.** If an agent doesn't read or answer within 15 minutes, or a machine is off, you get one note in the thread.
- **Each agent can have its own name and address.** A shared mailbox shows each agent's name on the sender line, and an agent with its own account uses it.
- **Works across machines with no server.** Each machine runs a small listener, and Gmail is the only thing they share.
- **One login method.** Every Google account logs in from a saved file, never the keychain, so it works over ssh and from scheduled jobs.

It's built on [agent-approvals](https://github.com/aelaguiz/agent-approvals), whose code finds and resumes sessions.

## Requirements

- macOS or Linux, [uv](https://docs.astral.sh/uv/), and Python 3.9 or newer as `python3`.
- The [Google Workspace CLI](https://github.com/googleworkspace/cli) (`gws`).
- [Herdr](https://herdr.dev), with agents running in its panes, to reach a running session. AI Manager's `aim` command, to resume a closed one or start a new one.
- An OAuth grant file for each Google account (see [A new login](#a-new-login)), with the Gmail modify scope.

## Install

```bash
git clone git@github.com:aelaguiz/agent-email.git
cd agent-email
make install MACHINE=laptop      # the first run creates ~/.agent-email/config.json and stops; fill it in, then run this again
make links                       # point gws and gws-<account> at the one Google command
make verify_install
```

`MACHINE` is this machine's fixed name, used once. `make links` saves whatever was at those paths in `~/.local/share/agent-email/old-wrappers/`. `scripts/rollout.sh` installs on other machines.

| Setting in `config.json` | What it is |
| --- | --- |
| `owner` | Your name, as agents see it. |
| `owner_addresses` | Every address you write from, aliases included. Only these count as you. The first is where system notes about held-back mail go. |
| `grants_dir` | The folder holding `gws-<account>-credentials.json` files. |
| `home_machine` | The machine that takes new emails and replies with no known sender. |
| `start_time` | Mail from before this is ignored, so old replies don't wake anyone. Set it when you install. |
| `machines` | Each machine's name and ssh route, for `accounts --fleet`. |
| `agent_domain` | The domain of agent mailboxes: account `chief` is `chief@<agent_domain>`. |
| `owner_accounts` | Your own accounts, by grant name. Agents never get these as a mailbox. A value is an agent address on that account, such as your plus address, for mail going only to you. |
| `default_account` | The owner account bare `gws` uses. `GWS_PROFILE` picks another of `owner_accounts`. |
| `start_command` | What starts a new session. |
| `agent_repos` | Repositories whose `.agent-identities.json` maps folders to agent names. |
| `folders` | For a working folder: which account sends and where email to you goes. The longest match wins. |
| `mailboxes` | Shared mailboxes and plus addresses: who handles new mail there, and in which folder. An agent with a grant of its own needs no entry, unless its address isn't `<account>@<agent_domain>` or its agent name isn't the account's: then an entry with `address` and `agent_id` makes that agent send from that address and get the mail sent to it. |

## Use

Agents learn it from the skill in [skills/agent-email](skills/agent-email/SKILL.md). By hand:

```bash
agent-email whoami                                # which agent this is, its address and yours
agent-email send --subject "Report" --body-file report.html --html -a chart.png
agent-email read EM-1a14d0ee                      # an email and anything else waiting for this session
agent-email reply EM-1a14d0ee --body "Done."      # answer everyone on that email, in its thread
agent-email done EM-1a14d0ee                      # it needs no answer
agent-email inbox                                 # what's waiting
agent-email accounts --fleet                      # every account, its address, and whether it works on each machine
agent-email doctor                                # this machine's setup
```

To give an agent an instruction, email its address. An agent with its own account has one. Any other agent can be reached through a shared mailbox with a plus address: `chief+cfo-specialist@example.com` goes to the agent named `cfo-specialist`.

## A new login

Each account's login is a grant file, `gws-<account>-credentials.json`, in `grants_dir`. That's the JSON `gws auth export --unmasked` prints: an `authorized_user` credential with a refresh token.

To add an account, put its grant there and run `agent-email links`, which creates `gws-<account>`. To replace one, for instance after a password change, make a new grant with a plain `gws auth login` in a config folder of its own, export it over the old file, and run `agent-email accounts` to check it. Copy the file to your other machines, or keep it in your secrets store.

## More

- [docs/design.md](docs/design.md): how it works and why.
- [docs/testing.md](docs/testing.md): the tests, and the live scenarios with real sessions and mail.
- [AGENTS.md](AGENTS.md): how to work on this repo.

## License

[MIT](LICENSE)
