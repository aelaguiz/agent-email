# Testing agent-email

## Unit tests

`make test` runs without network or real mail, using fakes for Gmail, Herdr and AI Manager. `tests/samples.py` holds real headers with the addresses changed. Add a test only for behavior that could really break, and never test the skill's wording.

`tests/test_gws_account.py` runs the real script with a fake `gws` under `/usr/bin/python3`, because on macOS that's the older Python it has to work on.

## Live scenarios

Unit tests can't prove the live path. A change to delivery, routing, the listener or the sender check is seen working here before it's done.

```bash
uv run python tests/live/drive.py <scenario>
```

Each scenario starts throwaway sessions in `tests/live/sandbox`, in their own Herdr session, so no real agent is touched. Real mail goes between the owner's accounts and the agent mailboxes, every subject says TEST, and `tests/live/drive.py archive` clears it afterward. Keep a real agent's mailbox off a test thread: his reply-all lands there too, and after the wait the home machine hands it to that agent's own session, as an earlier reply-all scenario did to a pod lead. When a test needs other people on a thread, use his own other mailboxes, which no agent watches. The addresses come from `private/live-test.json`, which holds:

```json
{"owner_default": "...", "owner_primary": "...", "owner_personal": "...", "owner_side": "...",
 "shared_mailbox": "chief@...", "agent_mailbox": "pod-member@...",
 "owner_cmd": "gws", "personal_cmd": "gws-personal", "side_cmd": "gws-side", "shared_cmd": "gws-chief", "agent_cmd": "gws-pod-member"}
```

While testing, add `tests/live` to `agent_repos` in the config, so a plus address can reach the sandbox as the agent `email-test`, and point `start_command` at a small model.

| Scenario | What it proves |
| --- | --- |
| `core` | Send, reply, notice, read, an instruction carried out, an answer, a second turn |
| `closed` | A closed session is resumed in a tab, then told |
| `content` | A changed subject; an attachment and a very long reply with a short notice |
| `replies` | Two quick replies; a listener restart with exactly one notice; every owner address; a plus address on the owner's own mailbox |
| `everyone` | A thread with several people: his reply-all reaches the session, and its answer goes to everyone his email went to, To and Cc as he left them, without the agent's own address, and arrives in each mailbox; a reply to the agent alone is answered to him alone |
| `new_mail` | A new email starts a session in the agent's folder; a second reaches that running session; a planted instruction in forwarded text is not obeyed |
| `unmatched` | A reply to an email no session sent reaches the mailbox's agent after the wait, told it isn't the sender |
| `two_sessions` | Two sessions in one conversation, each getting the reply to its own email |
| `codex` | An open and a closed Codex session |
| `fleet <machine>` | A session on another machine sends and closes, and a reply resumes it there |
| `fleet <machine> off` | The same with that machine's listener stopped: the reply waits, no other machine takes it, and it arrives when the listener is back |

Usage-limit and moved-copy handling is approvals' code, covered by its own tests and real use. The warnings are unit tested; to see a real one, age an inbound record by hand.

Close any Herdr panes a failed run leaves behind.
