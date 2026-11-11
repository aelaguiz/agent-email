# How agent-email works

## The pieces

| Piece | What it does | Where |
| --- | --- | --- |
| `bin/gws-account` | The one Google command. Linked as `gws` and `gws-<account>`. Logs in from a grant file, adds the agent's name to the sender, and starts a send record | `~/.local/share/agent-email/` |
| `agent-email` | Agents send, read and reply. Also records sends, and runs the listener | `~/.local/bin/` |
| Listener | Watches mailboxes, checks the sender, works out which machine owns each email, and tells sessions to read | launchd or systemd service, one per machine |
| Skill | Teaches agents to send and to hold a conversation by email | `skills/agent-email/` |

Each machine keeps its own records in `~/.agent-email/`. Gmail is the only thing machines share.

## Sending

Agents already send through a `gws-*` command, so that's where the capture goes. They don't have to adopt anything.

`gws-account` looks at its arguments. Anything that isn't a send becomes the real `gws` by `exec`, with no change in behavior. A send (`gmail +send`, `+reply`, `+reply-all`, `+forward`, `users messages send`, `users drafts send`) runs as a child, so the Gmail id it prints can be kept. Drafts and dry runs send nothing, so they're skipped.

After a send, it starts `agent-email record` detached. That writes a send record with what approvals' delivery code needs: runtime, session id, working folder and Herdr pane, all read from the session's own environment. It then adds the label `agent-email/from-<machine>` to the sent email. The email has already gone by then, so nothing here can fail a send. A label that fails is flagged in the record, and the listener retries it.

A send with no session behind it, such as a script run by a scheduler, gets a record but no label.

**The sender line.** Inside an agent session, `gws-account` adds `--from "<agent name> <mailbox>"`, using the name the session commits under, so a shared mailbox still shows who wrote each email. It leaves generic names alone, and it never touches the owner's own accounts, where an agent may be writing to someone else in his name. The one exception is an owner account with an agent address set, such as a plus address, and then only for mail going solely to the owner: that puts his reply at an address the listener can watch without reading the rest of his mailbox.

## Which machine owns a reply

Every listener reaches the same answer from what's in Gmail, so exactly one acts:

1. Take `In-Reply-To`, then `References` from its end, since that header lists the oldest message first. This finds the email he actually answered, and survives a changed subject, which splits the Gmail thread but keeps the headers.
2. Look each id up in the mailbox with `rfc822msgid:`. The nearest message with an `agent-email/from-<machine>` label names the owner.
3. That machine's send record names the session.

Where no message has a label, the reply waits 3 minutes and then goes to the mailbox's own agent, which is told it didn't send the email. That agent's mail, and a new email with no reply headers at all, belongs to the agent it's addressed to, on the machine where that agent is running: see [New mail](#new-mail).

**A machine that's off delays a reply; it never reroutes it.** A session can only resume on the machine it ran on, and another agent reading "Merge 9029" would have no idea what it refers to. After 30 minutes the home machine tells the owner the reply is waiting and why. Nothing ages out: the search runs from a fixed `start_time`, not a rolling window, so a reply is picked up however long its machine was off.

## The sweep

Every 30 seconds each listener runs one Gmail search per mailbox for mail from the owner's addresses that isn't yet read by an agent or held back. The home machine watches every mailbox. Others watch the mailboxes they have send records for, and those of the agents running on them right now: the agent's own, and the shared one that takes plus addresses for its folder. Outsiders' mail never comes back from this search unless it claims an owner address. The owner's own mailboxes are never searched, except for a configured plus address.

The list of mailboxes is read again at every sweep, so a login added or removed while the listener runs is watched or dropped without a restart. A mailbox that fails is logged and skipped. Nothing about one mailbox may stop the sweep, because delivery comes after it: on the night of November 6 a login removed while the listener ran stopped every sweep at its mailbox, and for nine hours nothing on that machine was delivered.

When a machine owns a reply, it writes the reply's record to disk first, then adds the `agent-email/received` label, then queues it. A restart finds pending records and queues them again.

## Telling the session

The input box gets one short fixed line, however long the email is:

```
[Email] Sam replied to "Project status". Read it: agent-email read EM-1a14d0ee
```

The email's own text never goes there. Typing long text into a terminal is fragile, and attachments can't go that way at all. The agent reads the email itself, which also proves it opened it.

Finding the session is approvals' `router.deliver`, imported rather than copied. It checks the transcript first, so a restart can't send twice. It looks for the session in its recorded pane and then in every pane, types the line, and confirms it in the transcript. A closed session is resumed through AI Manager in a new Herdr tab. For Claude it also skips a session stopped at a usage limit and follows moved copies and continuations. Codex sessions get the open and closed cases.

A failure retries after 5 minutes, then hourly after three failures, with one note to the owner.

If a session already has a notice it hasn't acted on, a second reply doesn't send another: one `agent-email read` shows everything waiting for that session.

**A session started again with none of the old one's history** isn't a moved copy or a continuation, so delivery can't tell it is the same agent, and a reply to the old session's email would resume the old session beside it. A pod restored from a save starts every member that way (November 8, 2026). So whatever restarts the agent runs `agent-email repoint <old> <new>` on the machine where the new session runs: every send record there naming the old session, and every reply it hasn't been told of yet, then names the new one (its folder and pane read from the running session), with the old id in `earlier_ids`. It refuses when the new session isn't running there or the old one still is. psbrain's `./pod restore` runs it for each restored member, beside approvals' `approvals repoint`.

## New mail

A new email is an instruction to an agent, so it goes where that agent is working. Agents run on different machines, and sending all their new mail to the home machine started a second copy of the agent there, without the work the first one had open.

**The machine where the agent is running takes it straight away.** "Running" means a Claude session on that machine whose working folder is the agent's folder: one of the folders in an agent repository's `.agent-identities.json`, or a configured mailbox's. A session in the user's home directory never counts, because a machine without the agent's repository uses that directory in place of the agent's folder. The machine writes the record and adds the `agent-email/received` label, as for any reply it owns.

**Where the agent is running nowhere, the home machine takes it,** 90 seconds on (`elsewhere_wait_seconds`), unless the label shows that another machine took it. That gives every listener three passes to see the email.

Either way, the email goes to the one Claude session in the agent's folder on that machine, if there is exactly one. Otherwise a new session starts there, in a tab of its own, and its id is saved before the notice goes in, so a retry doesn't start a second one.

Two machines running the same agent at once could both take the same email if they look within the same few seconds. Each checks the label first, which closes most of that gap.

## One shared mailbox

Only the configured mailboxes have Gmail. An agent's own Google login is a login only, so nobody pays for an inbox it doesn't read, and a new agent needs no setup here. It sends from its folder's mailbox under its own name. Google routes mail for its address (`<agent>@<agent_domain>`) into a shared mailbox, and the listener gives each email to the agent it was sent to, reading that from `X-Gm-Original-To`, which Google adds when it reroutes, and from the To line, which it leaves alone. A reply to an email an agent sent from its own address, before this, has no machine label in the shared mailbox, so it reaches that agent the same way. `gws-<account> gmail` refuses with a pointer to `agent-email`, because Google's own error doesn't say where the mail went. The login check asks such an account for a token rather than a mailbox profile. Settings are read again every pass, so a change reaches a running listener within one pass.

## An email that reached the wrong agent

He sometimes writes to the shared mailbox, or to one agent, about another's work. `agent-email handoff EM-... <agent>` makes it that agent's email: on the machine where that agent is running (asked over ssh), or the home machine if it runs nowhere, the email's record is written again for that agent and delivered like new mail, and the old record goes. The agent reads it as its own, and its answer goes in his thread, so his next reply comes back to it.

## Answering

`agent-email reply` answers in the thread and keeps everyone on the email it answers, as a reply-all does: the owner's address first, then that email's other To recipients in To and its Cc's in Cc, read from the email itself when the agent answers. The agent's own addresses come off: the mailbox it sends from, and the address his email reached it at, such as a plus address. So he decides who hears an answer by how he writes. A reply-all on a thread with several people gets an answer to all of them, and a reply to the agent alone gets an answer to him alone. `agent-email read` names whoever else is on his email, so the agent knows who it is writing for.

Another agent's mailbox on the thread gets the answer like anyone else, and nothing follows from it, because only mail from the owner reaches a session. Notes from the system go only to him.

## How we know it's you

The sessions this reaches run with full permissions, so `src/agent_email/sender.py` is the line between the owner and everyone on the internet.

A From line proves nothing, and domains with no DMARC policy get forged mail delivered. A passing signature from the owner's domain isn't enough either: a Google Group re-signs a stranger's mail with that domain and keeps the stranger's From line, so forged mail sent to a public group address arrives looking signed.

An email counts only if all of this holds:

- Its From is exactly one address, and it's one of `owner_addresses`.
- Google's own `Authentication-Results`, the topmost one, shows SPF passing for an envelope sender that is exactly one of those addresses. A group's envelope is `group+bounce@...`, so group mail fails here. A sender can write its own copy of that header, but Google's is added above it.
- That header shows a passing DKIM signature from the From address's own domain, or from the Google signing domain of one of the owner's domains.
- It has no mailing-list headers.
- It isn't an auto-reply, so a vacation responder never reaches an agent.

A plus address on the owner's own mailbox has no such header, because the mail never leaves it. The proof there is Gmail's Sent label on his own account.

Mail that fails is ignored and logged. If it claims to be the owner, he gets one note at his real address, so a real email of his that was misjudged can't vanish in silence.

Forwarded text inside his email isn't his. `agent-email read` marks where it starts and says to treat it as information, and the skill teaches why.

The check stops outsiders, not the owner's own agents, which hold his grants and could send as him.

## Keeping the owner informed

Silence reads as handled, so silence has to mean that. The agent's own answer is the receipt, and there are no delivery emails. He hears from the system only when something's wrong:

- an agent hasn't opened his email, or hasn't answered, 15 minutes on;
- delivery failed three times;
- a machine has been off with his reply for 30 minutes;
- mail claiming to be him failed the check;
- a login stopped working: the home machine checks every account once an hour.

## Logins

Each account has a grant file, and `gws-<account>` uses it with a token cache in `~/.config/gws-agents/<account>/`. It never touches the keychain, which is locked over ssh and from scheduled jobs. An account with no grant refuses to run rather than falling through to another identity, and a path that never exists stops gws falling back to the machine's gcloud login.

`gws auth login` is refused through these commands. A new grant is made and exported separately (see the README).
