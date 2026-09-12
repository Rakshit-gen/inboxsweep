"""Parses the List-Unsubscribe header and judges whether it's the kind
that's actually safe to act on automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_URI_RE = re.compile(r"<([^>]+)>")
_ONE_CLICK_VALUE = "list-unsubscribe=one-click"


@dataclass
class UnsubscribeInfo:
    mailto: str | None
    url: str | None
    one_click: bool

    @property
    def safe_to_automate(self) -> bool:
        """RFC 8058 one-click unsubscribe, an https link plus a
        List-Unsubscribe-Post header, is the only case treated as safe
        to act on without a human looking at it first. It's a real
        standard that major mail platforms implement correctly, and it
        doesn't involve visiting a page that could just be confirming
        to a spammer that the address is read. A bare mailto: or a link
        with no one-click header still gets reported, just not acted on
        automatically.
        """
        return self.one_click and self.url is not None and self.url.lower().startswith("https://")


def parse_list_unsubscribe(
    list_unsubscribe: str | None, list_unsubscribe_post: str | None
) -> UnsubscribeInfo | None:
    if not list_unsubscribe:
        return None

    uris = _URI_RE.findall(list_unsubscribe)
    mailto = next((u for u in uris if u.lower().startswith("mailto:")), None)
    url = next((u for u in uris if u.lower().startswith("http")), None)

    one_click = (
        list_unsubscribe_post is not None
        and list_unsubscribe_post.strip().lower() == _ONE_CLICK_VALUE
    )

    return UnsubscribeInfo(
        mailto=mailto,
        url=url,
        one_click=one_click,
    )
