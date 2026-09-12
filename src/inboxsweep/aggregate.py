"""Groups parsed messages by sender and ranks them by how much
clutter they've actually added.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from inboxsweep.headers import MessageInfo
from inboxsweep.unsubscribe import UnsubscribeInfo, parse_list_unsubscribe


@dataclass
class SenderSummary:
    sender_email: str
    sender_name: str
    count: int
    sample_subjects: list[str] = field(default_factory=list)
    unsubscribe: UnsubscribeInfo | None = None


def aggregate_by_sender(
    messages: list[MessageInfo], sample_size: int = 3
) -> list[SenderSummary]:
    groups: dict[str, list[MessageInfo]] = defaultdict(list)
    for m in messages:
        if m.sender_email:
            groups[m.sender_email].append(m)

    summaries = []
    for sender_email, msgs in groups.items():
        unsubscribe = None
        for m in msgs:
            info = parse_list_unsubscribe(m.list_unsubscribe, m.list_unsubscribe_post)
            if info is None:
                continue
            # Prefer whichever version of the header actually qualifies
            # as safe to automate, since a sender that's consistent
            # about it usually sends the same headers on every message,
            # but one that isn't shouldn't have its safe instance
            # buried by an earlier, less complete one.
            if unsubscribe is None or (info.safe_to_automate and not unsubscribe.safe_to_automate):
                unsubscribe = info

        summaries.append(
            SenderSummary(
                sender_email=sender_email,
                sender_name=msgs[0].sender_name,
                count=len(msgs),
                sample_subjects=[m.subject for m in msgs[:sample_size] if m.subject],
                unsubscribe=unsubscribe,
            )
        )

    summaries.sort(key=lambda s: s.count, reverse=True)
    return summaries
