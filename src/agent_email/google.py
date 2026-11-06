"""Gmail, reached directly from a saved grant. The listener watches dozens of mailboxes, so it doesn't start a gws
process for each one."""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

log = logging.getLogger("agent-email")
API = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GmailError(RuntimeError):
    pass


def _request(req, timeout=30):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise GmailError(f"{req.full_url.split('?')[0]}: {e.code} {e.read()[:300].decode('utf-8', 'replace')}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise GmailError(f"{req.full_url.split('?')[0]}: {e}") from None


class Account:
    def __init__(self, name, settings=None):
        self.name = name
        self.path = config.grant_path(name, settings)
        self._token, self._expires, self._labels = None, 0, None

    def token(self):
        if time.time() < self._expires - 60:
            return self._token
        grant = json.loads(self.path.read_text())
        data = urllib.parse.urlencode({"client_id": grant["client_id"], "client_secret": grant["client_secret"],
                                       "refresh_token": grant["refresh_token"], "grant_type": "refresh_token"})
        got = _request(urllib.request.Request(TOKEN_URL, data=data.encode()))
        self._token, self._expires = got["access_token"], time.time() + int(got.get("expires_in", 3600))
        return self._token

    def call(self, method, path, params=None, body=None):
        url = f"{API}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        headers = {"Authorization": f"Bearer {self.token()}"}
        data = None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        return _request(urllib.request.Request(url, data=data, headers=headers, method=method))

    def profile(self):
        return self.call("GET", "profile")

    def search(self, query, limit=50):
        return [m["id"] for m in self.call("GET", "messages", {"q": query, "maxResults": limit}).get("messages", [])]

    def metadata(self, message_id):
        return self.call("GET", f"messages/{message_id}", {"format": "metadata"})

    def full(self, message_id):
        return self.call("GET", f"messages/{message_id}", {"format": "full"})

    def thread(self, thread_id):
        return self.call("GET", f"threads/{thread_id}", {"format": "full"})

    def attachment(self, message_id, attachment_id):
        return self.call("GET", f"messages/{message_id}/attachments/{attachment_id}")["data"]

    def by_message_id(self, rfc822_id):
        """The mailbox's copy of a message, found by its Message-ID header."""
        found = self.search("rfc822msgid:" + rfc822_id.strip("<> "), 1)
        return self.metadata(found[0]) if found else None

    def labels(self):
        """Label names to ids. Fetched once per process, since labels only get added."""
        if self._labels is None:
            self._labels = {l["name"]: l["id"] for l in self.call("GET", "labels").get("labels", [])}
        return self._labels

    def label_id(self, name):
        known = self.labels()
        if name not in known:
            try:
                known[name] = self.call("POST", "labels", body={
                    "name": name, "labelListVisibility": "labelHide", "messageListVisibility": "hide"})["id"]
            except GmailError:      # another machine made it first
                self._labels = None
                return self.labels()[name]
        return known[name]

    def label_names(self, label_ids):
        ids = {v: k for k, v in self.labels().items()}
        names = [ids[i] for i in label_ids if i in ids]
        if len(names) < len(label_ids):      # a label another machine made since this one last looked
            self._labels = None
            ids = {v: k for k, v in self.labels().items()}
            names = [ids.get(i, i) for i in label_ids]
        return names

    def add_label(self, message_id, name):
        self.call("POST", f"messages/{message_id}/modify", body={"addLabelIds": [self.label_id(name)]})
