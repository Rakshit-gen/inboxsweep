"""Parses the headers of a single email into a plain structure.

Only headers are ever touched, never message bodies, both because
that's all a clutter report needs and because fetching just headers
over IMAP (with BODY.PEEK) is what lets scanning happen without marking
anything as read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes, policy
from email.utils import parseaddr, parsedate_to_datetime


@dataclass
class MessageInfo:
    sender_name: str
    sender_email: str
    subject: str
    date: datetime | None
    list_unsubscribe: str | None
    list_unsubscribe_post: str | None


def parse_message(raw_headers: bytes) -> MessageInfo:
    msg = message_from_bytes(raw_headers, policy=policy.default)

    name, email_addr = parseaddr(str(msg.get("From", "")))

    # policy.default parses the Date header eagerly, so on some Python
    # versions (3.9) a malformed date raises TypeError right out of
    # msg.get("Date") itself, before parsedate_to_datetime is ever
    # called explicitly below. Both the fetch and the explicit parse
    # need to be guarded.
    try:
        raw_date = msg.get("Date")
    except (TypeError, ValueError):
        raw_date = None

    date = None
    if raw_date:
        try:
            date = parsedate_to_datetime(str(raw_date))
        except (TypeError, ValueError):
            date = None

    return MessageInfo(
        sender_name=name,
        sender_email=email_addr.lower(),
        subject=str(msg.get("Subject", "")),
        date=date,
        list_unsubscribe=_clean_header(msg.get("List-Unsubscribe")),
        list_unsubscribe_post=_clean_header(msg.get("List-Unsubscribe-Post")),
    )


def _clean_header(value) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None
