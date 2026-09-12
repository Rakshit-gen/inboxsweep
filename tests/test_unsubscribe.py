import unittest

from inboxsweep.unsubscribe import parse_list_unsubscribe


class TestParseListUnsubscribe(unittest.TestCase):
    def test_none_header_returns_none(self):
        self.assertIsNone(parse_list_unsubscribe(None, None))

    def test_extracts_mailto_and_url(self):
        info = parse_list_unsubscribe(
            "<mailto:unsub@example.com>, <https://example.com/unsub?id=1>", None
        )
        self.assertEqual(info.mailto, "mailto:unsub@example.com")
        self.assertEqual(info.url, "https://example.com/unsub?id=1")

    def test_one_click_requires_post_header(self):
        info = parse_list_unsubscribe("<https://example.com/unsub>", None)
        self.assertFalse(info.one_click)
        self.assertFalse(info.safe_to_automate)

    def test_full_rfc8058_is_safe_to_automate(self):
        info = parse_list_unsubscribe(
            "<https://example.com/unsub>", "List-Unsubscribe=One-Click"
        )
        self.assertTrue(info.one_click)
        self.assertTrue(info.safe_to_automate)

    def test_mailto_only_is_never_safe_to_automate(self):
        # Even with a one-click post header present, a bare mailto with
        # no https URL isn't something inboxsweep will act on for you,
        # sending an email on your behalf is a bigger step than a link.
        info = parse_list_unsubscribe(
            "<mailto:unsub@example.com>", "List-Unsubscribe=One-Click"
        )
        self.assertIsNone(info.url)
        self.assertFalse(info.safe_to_automate)

    def test_plain_http_is_not_safe_to_automate(self):
        # Plain http (not https) shouldn't be treated as safe even with
        # a one-click header, credentials/tokens in the URL over an
        # unencrypted connection is exactly the kind of thing worth
        # being conservative about.
        info = parse_list_unsubscribe(
            "<http://example.com/unsub>", "List-Unsubscribe=One-Click"
        )
        self.assertFalse(info.safe_to_automate)

    def test_post_header_with_wrong_value_is_not_one_click(self):
        # Regression test: the header only means what RFC 8058 says it
        # means when its value is exactly "List-Unsubscribe=One-Click".
        # Treating any non-empty value as one-click would let a sender
        # that sets this header for some unrelated reason get
        # misclassified as safe to automate.
        info = parse_list_unsubscribe("<https://example.com/unsub>", "something-else")
        self.assertFalse(info.one_click)
        self.assertFalse(info.safe_to_automate)

    def test_no_valid_uris_gives_none_fields(self):
        info = parse_list_unsubscribe("garbage, no angle brackets", None)
        self.assertIsNone(info.mailto)
        self.assertIsNone(info.url)
        self.assertFalse(info.safe_to_automate)


if __name__ == "__main__":
    unittest.main()
