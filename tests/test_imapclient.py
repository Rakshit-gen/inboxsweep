import unittest
from datetime import date
from unittest import mock

from inboxsweep.imapclient import Credentials, ImapError, MailClient


class FakeConn:
    def __init__(self):
        self.selected = None
        self.stored = []
        self.copied = []
        self.expunged = False

    def select(self, folder):
        self.selected = folder
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        if criteria[0] == "SINCE":
            return "OK", [b"1 2 3"]
        if criteria[0] == "FROM":
            return "OK", [b"5 6"]
        return "OK", [b""]

    def fetch(self, msg_id, spec):
        return "OK", [(f"{msg_id} (BODY[HEADER] {{10}}".encode(), b"From: a@b.com\r\n\r\n")]

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


class TestMailClient(unittest.TestCase):
    def setUp(self):
        self.fake = FakeConn()
        self.creds = Credentials(host="imap.example.com", user="me@example.com", password="pw")
        self.client = MailClient(self.creds, connection=self.fake)

    def test_select_ok(self):
        self.client.select("INBOX")
        self.assertEqual(self.fake.selected, "INBOX")

    def test_search_since_returns_ids(self):
        ids = self.client.search_since(date(2026, 1, 1))
        self.assertEqual(ids, ["1", "2", "3"])

    def test_search_from_returns_ids(self):
        ids = self.client.search_from("news@example.com")
        self.assertEqual(ids, ["5", "6"])

    def test_fetch_headers_returns_raw_bytes(self):
        raw = self.client.fetch_headers("1")
        self.assertEqual(raw, b"From: a@b.com\r\n\r\n")

    def test_move_to_folder_copies_deletes_and_expunges(self):
        self.client.move_to_folder(["1", "2"], "Archive")
        self.assertEqual(self.fake.copied, [("1,2", "Archive")])
        self.assertTrue(self.fake.expunged)
        self.assertEqual(self.fake.stored[0][0], "1,2")

    def test_move_to_folder_with_no_ids_does_nothing(self):
        self.client.move_to_folder([], "Archive")
        self.assertEqual(self.fake.copied, [])
        self.assertFalse(self.fake.expunged)

    def test_delete_marks_and_expunges(self):
        self.client.delete(["7"])
        self.assertEqual(self.fake.stored[0][0], "7")
        self.assertTrue(self.fake.expunged)

    def test_delete_with_no_ids_does_nothing(self):
        self.client.delete([])
        self.assertEqual(self.fake.stored, [])
        self.assertFalse(self.fake.expunged)

    def test_context_manager_closes_on_exit(self):
        with MailClient(self.creds, connection=self.fake) as client:
            pass
        self.assertIsNone(client._conn)


class TestMailClientConnect(unittest.TestCase):
    def setUp(self):
        self.creds = Credentials(host="imap.example.com", user="me@example.com", password="pw")

    def test_connect_raises_on_login_failure(self):
        with mock.patch("inboxsweep.imapclient.imaplib.IMAP4_SSL") as mock_imap:
            mock_imap.return_value.login.return_value = ("NO", [b"auth failed"])
            client = MailClient(self.creds)
            with self.assertRaises(ImapError):
                client.connect()

    def test_connect_reuses_existing_connection(self):
        with mock.patch("inboxsweep.imapclient.imaplib.IMAP4_SSL") as mock_imap:
            mock_imap.return_value.login.return_value = ("OK", [b"welcome"])
            client = MailClient(self.creds)
            client.connect()
            first_conn = client._conn
            client.connect()
            self.assertIs(client._conn, first_conn)
            mock_imap.assert_called_once()


if __name__ == "__main__":
    unittest.main()
