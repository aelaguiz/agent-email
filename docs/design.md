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

Where no message has a label, the home machine takes the reply after 3 minutes, as a reply to the mailbox's own agent, and tells that session it didn't send the email. A new email, with no reply headers at all, goes to the home machine straight away.

**A machine that's off delays a reply; it never reroutes it.** A session can only resume on the machine it ran on, and another agent reading "Merge 9029" would have no idea what it refers to. After 30 minutes the home machine tells the owner the reply is waiting and why. Nothing ages out: the search runs from a fixed `start_time`, not a rolling window, so a reply is picked up however long its machine was off.

## The sweep

Every 30 seconds each listener runs one Gmail search per mailbox for mail from the owner's addresses that isn't yet read by an agent or held back. The home machine watches every mailbox; others watch only mailboxes they have send records for. Outsiders' mail never comes back from this search unless it claims an owner address. The owner's own mailboxes are never searched, except for a configured plus address.

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

**A new email** goes to the one Claude session running in the agent's folder, if there is exactly one. Otherwise a new session starts there, in a tab of its own, and its id is saved before the notice goes in, so a retry doesn't start a second one.

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
