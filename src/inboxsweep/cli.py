"""Command line interface for inboxsweep.

The core operations (scan, archive, delete) take an already-connected
MailClient and contain no argparse or environment-variable logic, so
they can be tested directly against a fake connection. The cmd_*
functions are the thin layer that wires real credentials and CLI flags
into those operations.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta

from inboxsweep.aggregate import SenderSummary, aggregate_by_sender
from inboxsweep.headers import parse_message
from inboxsweep.imapclient import Credentials, ImapError, MailClient

_SINCE_RE = re.compile(r"^(\d+)([dwh])$")


def parse_since(value: str) -> date:
    match = _SINCE_RE.match(value.strip())
    if not match:
        raise ValueError(f"--since must look like 90d, 12w, or 48h, got {value!r}")
    amount, unit = int(match.group(1)), match.group(2)
    delta = {"d": timedelta(days=amount), "w": timedelta(weeks=amount), "h": timedelta(hours=amount)}[unit]
    return (datetime.now() - delta).date()


def load_credentials() -> Credentials:
    host = os.environ.get("INBOXSWEEP_HOST")
    user = os.environ.get("INBOXSWEEP_USER")
    password = os.environ.get("INBOXSWEEP_PASS")
    missing = [
        name
        for name, value in [
            ("INBOXSWEEP_HOST", host),
            ("INBOXSWEEP_USER", user),
            ("INBOXSWEEP_PASS", password),
        ]
        if not value
    ]
    if missing:
        raise SystemExit(
            "inboxsweep: missing environment variables: " + ", ".join(missing)
        )
    return Credentials(host=host, user=user, password=password)


def scan(client: MailClient, folder: str, since: date) -> list[SenderSummary]:
    client.select(folder)
    ids = client.search_since(since)
    messages = [parse_message(client.fetch_headers(i)) for i in ids]
    return aggregate_by_sender(messages)


def find_sender_messages(client: MailClient, folder: str, sender: str) -> list[str]:
    client.select(folder)
    return client.search_from(sender)


def format_report(summaries: list[SenderSummary]) -> str:
    if not summaries:
        return "No messages found in that window."

    lines = [f"{'Sender':<35}{'Count':>7}  Unsubscribe"]
    for s in summaries:
        if s.unsubscribe is None:
            unsub = "no unsubscribe link found"
        elif s.unsubscribe.safe_to_automate:
            unsub = f"one-click, verified safe: {s.unsubscribe.url}"
        elif s.unsubscribe.url:
            unsub = f"link present, verify manually: {s.unsubscribe.url}"
        elif s.unsubscribe.mailto:
            unsub = f"mailto only, verify manually: {s.unsubscribe.mailto}"
        else:
            unsub = "unsubscribe header present but unparseable"
        lines.append(f"{s.sender_email:<35}{s.count:>7}  {unsub}")
    return "\n".join(lines)


def cmd_scan(args: argparse.Namespace) -> int:
    creds = load_credentials()
    try:
        since = parse_since(args.since)
    except ValueError as e:
        print(f"inboxsweep: {e}", file=sys.stderr)
        return 1
    try:
        with MailClient(creds) as client:
            summaries = scan(client, args.folder, since)
    except ImapError as e:
        print(f"inboxsweep: {e}", file=sys.stderr)
        return 1
    print(format_report(summaries))
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    creds = load_credentials()
    try:
        with MailClient(creds) as client:
            ids = find_sender_messages(client, args.folder, args.sender)
            if not ids:
                print(f"No messages from {args.sender} in {args.folder}.")
                return 0
            if not args.apply:
                print(f"Would move {len(ids)} message(s) from {args.sender} to {args.to_folder}.")
                return 0
            client.move_to_folder(ids, args.to_folder)
            print(f"Moved {len(ids)} message(s) from {args.sender} to {args.to_folder}.")
    except ImapError as e:
        print(f"inboxsweep: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    creds = load_credentials()
    try:
        with MailClient(creds) as client:
            ids = find_sender_messages(client, args.folder, args.sender)
            if not ids:
                print(f"No messages from {args.sender} in {args.folder}.")
                return 0
            if not args.apply:
                print(f"Would delete {len(ids)} message(s) from {args.sender}.")
                return 0
            client.delete(ids)
            print(f"Deleted {len(ids)} message(s) from {args.sender}.")
    except ImapError as e:
        print(f"inboxsweep: {e}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="inboxsweep")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="rank senders cluttering a folder")
    scan_p.add_argument("--since", default="90d")
    scan_p.add_argument("--folder", default="INBOX")
    scan_p.set_defaults(func=cmd_scan)

    archive_p = sub.add_parser("archive", help="move a sender's messages to another folder")
    archive_p.add_argument("--sender", required=True)
    archive_p.add_argument("--folder", default="INBOX")
    archive_p.add_argument("--to-folder", default="Archive")
    archive_p.add_argument("--apply", action="store_true")
    archive_p.set_defaults(func=cmd_archive)

    delete_p = sub.add_parser("delete", help="permanently delete a sender's messages")
    delete_p.add_argument("--sender", required=True)
    delete_p.add_argument("--folder", default="INBOX")
    delete_p.add_argument("--apply", action="store_true")
    delete_p.set_defaults(func=cmd_delete)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
