import argparse
import contextlib
import io
import os
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

from inboxsweep.aggregate import SenderSummary
from inboxsweep.cli import (
    cmd_archive,
    cmd_delete,
    cmd_scan,
    find_sender_messages,
    format_report,
    load_credentials,
    parse_since,
    scan,
)
from inboxsweep.imapclient import Credentials, MailClient

CREDS = Credentials(host="imap.example.com", user="me@example.com", password="pw")


class FakeConn:
    def __init__(self, search_results=None, fetch_results=None):
        self.search_results = search_results or {}
        self.fetch_results = fetch_results or {}
        self.stored = []
        self.copied = []
        self.expunged = False
        self.selected = None

    def select(self, folder):
        self.selected = folder
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        ids = self.search_results.get(criteria[0], [])
        return "OK", [" ".join(ids).encode()]

    def fetch(self, msg_id, spec):
        raw = self.fetch_results.get(msg_id, b"From: nobody@example.com\r\n\r\n")
        return "OK", [(b"header", raw)]

    def copy(self, id_set, folder):
        self.copied.append((id_set, folder))
        return "OK", [b"copied"]

    def store(self, id_set, flag_action, flags):
        self.stored.append((id_set, flag_action, flags))
        return "OK", [b"stored"]

    def expunge(self):
        self.expunged = True
        return "OK", [b"1"]

    def logout(self):
        return "OK", [b"bye"]


class TestParseSince(unittest.TestCase):
    def test_days(self):
        result = parse_since("1d")
        expected = (datetime.now() - timedelta(days=1)).date()
        self.assertEqual(result, expected)

    def test_weeks(self):
        result = parse_since("2w")
        expected = (datetime.now() - timedelta(weeks=2)).date()
        self.assertEqual(result, expected)

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            parse_since("not a duration")

    def test_missing_unit_raises(self):
        with self.assertRaises(ValueError):
            parse_since("90")


class TestScanLogic(unittest.TestCase):
    def test_scan_selects_folder_and_aggregates(self):
        fake = FakeConn(
            search_results={"SINCE": ["1", "2", "3"]},
            fetch_results={
                "1": b"From: news@a.com\r\nSubject: Hi\r\n\r\n",
                "2": b"From: news@a.com\r\nSubject: Hi again\r\n\r\n",
                "3": b"From: shop@b.com\r\nSubject: Sale\r\n\r\n",
            },
        )
        client = MailClient(CREDS, connection=fake)
        summaries = scan(client, "INBOX", date(2026, 1, 1))
        self.assertEqual(fake.selected, "INBOX")
        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0].sender_email, "news@a.com")
        self.assertEqual(summaries[0].count, 2)


class TestScanMinCount(unittest.TestCase):
    def test_min_count_filters_out_small_senders(self):
        fake = FakeConn(
            search_results={"SINCE": ["1", "2", "3"]},
            fetch_results={
                "1": b"From: frequent@a.com\r\n\r\n",
                "2": b"From: frequent@a.com\r\n\r\n",
                "3": b"From: rare@b.com\r\n\r\n",
            },
        )
        client = MailClient(CREDS, connection=fake)
        summaries = scan(client, "INBOX", date(2026, 1, 1), min_count=2)
        senders = [s.sender_email for s in summaries]
        self.assertEqual(senders, ["frequent@a.com"])

    def test_min_count_one_keeps_everything(self):
        fake = FakeConn(
            search_results={"SINCE": ["1"]},
            fetch_results={"1": b"From: a@a.com\r\n\r\n"},
        )
        client = MailClient(CREDS, connection=fake)
        summaries = scan(client, "INBOX", date(2026, 1, 1), min_count=1)
        self.assertEqual(len(summaries), 1)


class TestFormatReport(unittest.TestCase):
    def test_empty_report(self):
        self.assertIn("No messages", format_report([]))

    def test_no_unsubscribe_info(self):
        summaries = [SenderSummary(sender_email="a@a.com", sender_name="A", count=5)]
        report = format_report(summaries)
        self.assertIn("a@a.com", report)
        self.assertIn("no unsubscribe link found", report)


class TestFindSenderMessages(unittest.TestCase):
    def test_returns_matching_ids(self):
        fake = FakeConn(
            search_results={"FROM": ["10", "11"]},
            fetch_results={
                "10": b"From: news@a.com\r\n\r\n",
                "11": b"From: news@a.com\r\n\r\n",
            },
        )
        client = MailClient(CREDS, connection=fake)
        ids = find_sender_messages(client, "INBOX", "news@a.com")
        self.assertEqual(ids, ["10", "11"])

    def test_filters_out_imap_substring_false_positives(self):
        # Regression test: IMAP's SEARCH FROM matches substrings of the
        # whole From header, so a search for "news@a.com" used to also
        # return a message actually from "othernews@a.com" as long as
        # the server's search considered it a match.
        fake = FakeConn(
            search_results={"FROM": ["10", "11"]},
            fetch_results={
                "10": b"From: news@a.com\r\n\r\n",
                "11": b"From: othernews@a.com\r\n\r\n",
            },
        )
        client = MailClient(CREDS, connection=fake)
        ids = find_sender_messages(client, "INBOX", "news@a.com")
        self.assertEqual(ids, ["10"])

    def test_sender_match_is_case_insensitive(self):
        fake = FakeConn(
            search_results={"FROM": ["10"]},
            fetch_results={"10": b"From: NEWS@A.COM\r\n\r\n"},
        )
        client = MailClient(CREDS, connection=fake)
        ids = find_sender_messages(client, "INBOX", "news@a.com")
        self.assertEqual(ids, ["10"])


class TestLoadCredentials(unittest.TestCase):
    def test_missing_vars_exits(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                load_credentials()

    def test_present_vars_returns_credentials(self):
        env = {"INBOXSWEEP_HOST": "h", "INBOXSWEEP_USER": "u", "INBOXSWEEP_PASS": "p"}
        with mock.patch.dict(os.environ, env, clear=True):
            creds = load_credentials()
            self.assertEqual(creds.host, "h")
            self.assertEqual(creds.user, "u")
            self.assertEqual(creds.password, "p")


class TestCmdScanIntegration(unittest.TestCase):
    def test_full_scan_command_prints_report(self):
        fake = FakeConn(
            search_results={"SINCE": ["1"]},
            fetch_results={"1": b"From: news@a.com\r\nSubject: Hi\r\n\r\n"},
        )
        real_client = MailClient(CREDS, connection=fake)
        env = {"INBOXSWEEP_HOST": "h", "INBOXSWEEP_USER": "u", "INBOXSWEEP_PASS": "p"}

        with mock.patch.dict(os.environ, env, clear=True), mock.patch(
            "inboxsweep.cli.MailClient", return_value=real_client
        ):
            args = argparse.Namespace(since="90d", folder="INBOX", min_count=1)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cmd_scan(args)

        self.assertEqual(code, 0)
        self.assertIn("news@a.com", out.getvalue())


class TestCmdScanBadSince(unittest.TestCase):
    def test_malformed_since_is_a_clean_error_not_a_crash(self):
        # Regression test: a bad --since value used to raise an
        # unhandled ValueError all the way out of main(), printing a
        # full traceback instead of a one-line usage error.
        env = {"INBOXSWEEP_HOST": "h", "INBOXSWEEP_USER": "u", "INBOXSWEEP_PASS": "p"}
        with mock.patch.dict(os.environ, env, clear=True):
            args = argparse.Namespace(since="garbage", folder="INBOX")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = cmd_scan(args)
        self.assertEqual(code, 1)
        self.assertIn("--since", err.getvalue())


class TestCmdArchiveIntegration(unittest.TestCase):
    ENV = {"INBOXSWEEP_HOST": "h", "INBOXSWEEP_USER": "u", "INBOXSWEEP_PASS": "p"}

    def test_dry_run_does_not_move_anything(self):
        fake = FakeConn(
            search_results={"FROM": ["1", "2"]},
            fetch_results={
                "1": b"From: news@a.com\r\n\r\n",
                "2": b"From: news@a.com\r\n\r\n",
            },
        )
        real_client = MailClient(CREDS, connection=fake)

        with mock.patch.dict(os.environ, self.ENV, clear=True), mock.patch(
            "inboxsweep.cli.MailClient", return_value=real_client
        ):
            args = argparse.Namespace(
                sender="news@a.com", folder="INBOX", to_folder="Archive", apply=False
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cmd_archive(args)

        self.assertEqual(code, 0)
        self.assertIn("Would move 2", out.getvalue())
        self.assertEqual(fake.copied, [])
        self.assertFalse(fake.expunged)

    def test_apply_actually_moves(self):
        fake = FakeConn(
            search_results={"FROM": ["1", "2"]},
            fetch_results={
                "1": b"From: news@a.com\r\n\r\n",
                "2": b"From: news@a.com\r\n\r\n",
            },
        )
        real_client = MailClient(CREDS, connection=fake)

        with mock.patch.dict(os.environ, self.ENV, clear=True), mock.patch(
            "inboxsweep.cli.MailClient", return_value=real_client
        ):
            args = argparse.Namespace(
                sender="news@a.com", folder="INBOX", to_folder="Archive", apply=True
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cmd_archive(args)

        self.assertEqual(code, 0)
        self.assertIn("Moved 2", out.getvalue())
        self.assertEqual(fake.copied, [("1,2", "Archive")])
        self.assertTrue(fake.expunged)

    def test_no_matching_messages(self):
        fake = FakeConn(search_results={"FROM": []})
        real_client = MailClient(CREDS, connection=fake)

        with mock.patch.dict(os.environ, self.ENV, clear=True), mock.patch(
            "inboxsweep.cli.MailClient", return_value=real_client
        ):
            args = argparse.Namespace(
                sender="ghost@a.com", folder="INBOX", to_folder="Archive", apply=True
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cmd_archive(args)

        self.assertEqual(code, 0)
        self.assertIn("No messages", out.getvalue())
        self.assertEqual(fake.copied, [])


class TestCmdDeleteIntegration(unittest.TestCase):
    ENV = {"INBOXSWEEP_HOST": "h", "INBOXSWEEP_USER": "u", "INBOXSWEEP_PASS": "p"}

    def test_dry_run_does_not_delete_anything(self):
        fake = FakeConn(
            search_results={"FROM": ["7"]},
            fetch_results={"7": b"From: spam@a.com\r\n\r\n"},
        )
        real_client = MailClient(CREDS, connection=fake)

        with mock.patch.dict(os.environ, self.ENV, clear=True), mock.patch(
            "inboxsweep.cli.MailClient", return_value=real_client
        ):
            args = argparse.Namespace(sender="spam@a.com", folder="INBOX", apply=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cmd_delete(args)

        self.assertEqual(code, 0)
        self.assertIn("Would delete 1", out.getvalue())
        self.assertEqual(fake.stored, [])
        self.assertFalse(fake.expunged)

    def test_apply_actually_deletes(self):
        fake = FakeConn(
            search_results={"FROM": ["7"]},
            fetch_results={"7": b"From: spam@a.com\r\n\r\n"},
        )
        real_client = MailClient(CREDS, connection=fake)

        with mock.patch.dict(os.environ, self.ENV, clear=True), mock.patch(
            "inboxsweep.cli.MailClient", return_value=real_client
        ):
            args = argparse.Namespace(sender="spam@a.com", folder="INBOX", apply=True)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cmd_delete(args)

        self.assertEqual(code, 0)
        self.assertIn("Deleted 1", out.getvalue())
        self.assertTrue(fake.expunged)


if __name__ == "__main__":
    unittest.main()
