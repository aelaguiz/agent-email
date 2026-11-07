import samples as s
from agent_email import cli


def test_an_answer_goes_to_everyone_on_his_email_but_the_agent():
    """His reply-all keeps its To and Cc lists, without the agent's mailbox or the plus address his email reached it at."""
    headers = s.h(Delivered_To="chief+cfo@example.com", From="Owner Name <owner@example.org>",
                  To='Chief <chief@example.com>, "Lee, Sam" <sam@example.net>, chief+cfo@example.com',
                  Cc="pat@example.net, Owner Name <OWNER@example.org>")
    item = {"reply_to": "owner@example.org", "mailbox": "chief@example.com"}
    assert cli.recipients(item, headers) == (["owner@example.org", "sam@example.net"], ["pat@example.net"])


def test_a_reply_to_the_agent_alone_is_answered_to_him_alone():
    item = {"reply_to": "owner@example.org", "mailbox": "agent@example.com"}
    assert cli.recipients(item, s.DEFAULT_SENDER) == (["owner@example.org"], [])
