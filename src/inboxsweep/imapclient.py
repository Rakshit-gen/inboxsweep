"""A thin wrapper around imaplib for exactly the operations inboxsweep
needs. The underlying connection can be injected, which is what makes
the rest of this testable without a real mail server.
"""

from __future__ import annotations

import imaplib
from dataclasses import dataclass
from datetime import date


class ImapError(Exception):
    pass


@dataclass
class Credentials:
    host: str
    user: str
    password: str
    port: int = 993


class MailClient:
    def __init__(self, creds: Credentials, connection=None):
        self.creds = creds
        self._conn = connection

    def __enter__(self) -> "MailClient":
        self.connect()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def connect(self) -> None:
        if self._conn is not None:
            return
        conn = imaplib.IMAP4_SSL(self.creds.host, self.creds.port)
        typ, _ = conn.login(self.creds.user, self.creds.password)
        if typ != "OK":
            try:
                conn.logout()
            except Exception:
                pass
            raise ImapError(f"login failed for {self.creds.user}")
        self._conn = conn

    def close(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.logout()
        except Exception:
            pass
        self._conn = None

    def select(self, folder: str = "INBOX") -> None:
        typ, _ = self._conn.select(folder)
        if typ != "OK":
            raise ImapError(f"couldn't select folder {folder!r}")

    def search_since(self, since: date) -> list[str]:
        criterion = since.strftime("%d-%b-%Y")
        typ, data = self._conn.search(None, "SINCE", criterion)
        if typ != "OK":
            raise ImapError("search failed")
        return [i.decode() for i in data[0].split()]

    def search_from(self, sender_email: str) -> list[str]:
        typ, data = self._conn.search(None, "FROM", f'"{sender_email}"')
        if typ != "OK":
            raise ImapError("search failed")
        return [i.decode() for i in data[0].split()]

    def fetch_headers(self, msg_id: str) -> bytes:
        typ, data = self._conn.fetch(msg_id, "(BODY.PEEK[HEADER])")
        if typ != "OK":
            raise ImapError(f"fetch failed for message {msg_id}")
        for part in data:
            if isinstance(part, tuple):
                return part[1]
        raise ImapError(f"unexpected fetch response for message {msg_id}")

    def move_to_folder(self, msg_ids: list[str], target_folder: str) -> None:
        if not msg_ids:
            return
        id_set = ",".join(msg_ids)
        typ, _ = self._conn.copy(id_set, target_folder)
        if typ != "OK":
            raise ImapError(f"copy to {target_folder!r} failed")
        typ, _ = self._conn.store(id_set, "+FLAGS", r"(\Deleted)")
        if typ != "OK":
            raise ImapError(f"marking messages deleted failed")
        self._conn.expunge()

    def delete(self, msg_ids: list[str]) -> None:
        if not msg_ids:
            return
        id_set = ",".join(msg_ids)
        typ, _ = self._conn.store(id_set, "+FLAGS", r"(\Deleted)")
        if typ != "OK":
            raise ImapError(f"marking messages deleted failed")
        self._conn.expunge()
