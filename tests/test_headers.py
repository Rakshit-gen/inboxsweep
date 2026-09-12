import unittest
from datetime import timezone

from inboxsweep.headers import parse_message


def build_raw(headers: dict) -> bytes:
    lines = [f"{k}: {v}" for k, v in headers.items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


class TestParseMessage(unittest.TestCase):
    def test_basic_fields(self):
        raw = build_raw(
            {
                "From": "Newsletter <news@example.com>",
                "Subject": "Weekly digest",
                "Date": "Tue, 01 Sep 2026 10:00:00 +0000",
            }
        )
        info = parse_message(raw)
        self.assertEqual(info.sender_name, "Newsletter")
        self.assertEqual(info.sender_email, "news@example.com")
        self.assertEqual(info.subject, "Weekly digest")
        self.assertEqual(info.date.year, 2026)
        self.assertEqual(info.date.tzinfo, timezone.utc)

    def test_sender_email_is_lowercased(self):
        raw = build_raw({"From": "Someone <SOMEONE@Example.COM>"})
        info = parse_message(raw)
        self.assertEqual(info.sender_email, "someone@example.com")

    def test_missing_unsubscribe_headers_are_none(self):
        raw = build_raw({"From": "a@b.com"})
        info = parse_message(raw)
        self.assertIsNone(info.list_unsubscribe)
        self.assertIsNone(info.list_unsubscribe_post)

    def test_list_unsubscribe_headers_are_captured(self):
        raw = build_raw(
            {
                "From": "a@b.com",
                "List-Unsubscribe": "<mailto:unsub@example.com>, <https://example.com/unsub>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        )
        info = parse_message(raw)
        self.assertIn("mailto:unsub@example.com", info.list_unsubscribe)
        self.assertEqual(info.list_unsubscribe_post, "List-Unsubscribe=One-Click")

    def test_malformed_date_does_not_raise(self):
        raw = build_raw({"From": "a@b.com", "Date": "not a real date"})
        info = parse_message(raw)
        self.assertIsNone(info.date)

    def test_missing_from_gives_empty_sender(self):
        raw = build_raw({"Subject": "no sender here"})
        info = parse_message(raw)
        self.assertEqual(info.sender_email, "")


if __name__ == "__main__":
    unittest.main()
