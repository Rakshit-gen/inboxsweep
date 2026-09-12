import unittest

from inboxsweep.aggregate import aggregate_by_sender
from inboxsweep.headers import MessageInfo


def msg(sender_email, subject="", sender_name="", list_unsub=None, list_unsub_post=None):
    return MessageInfo(
        sender_name=sender_name,
        sender_email=sender_email,
        subject=subject,
        date=None,
        list_unsubscribe=list_unsub,
        list_unsubscribe_post=list_unsub_post,
    )


class TestAggregateBySender(unittest.TestCase):
    def test_groups_and_counts(self):
        messages = [
            msg("news@a.com", "Digest 1"),
            msg("news@a.com", "Digest 2"),
            msg("shop@b.com", "Sale"),
        ]
        summaries = aggregate_by_sender(messages)
        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0].sender_email, "news@a.com")
        self.assertEqual(summaries[0].count, 2)
        self.assertEqual(summaries[1].count, 1)

    def test_sorted_by_count_descending(self):
        messages = [msg("small@a.com")] + [msg("big@b.com") for _ in range(5)]
        summaries = aggregate_by_sender(messages)
        self.assertEqual(summaries[0].sender_email, "big@b.com")

    def test_sample_subjects_capped(self):
        messages = [msg("a@a.com", subject=f"Subject {i}") for i in range(10)]
        summaries = aggregate_by_sender(messages, sample_size=3)
        self.assertEqual(len(summaries[0].sample_subjects), 3)

    def test_messages_without_sender_are_skipped(self):
        messages = [msg(""), msg("real@a.com")]
        summaries = aggregate_by_sender(messages)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].sender_email, "real@a.com")

    def test_picks_first_non_empty_sender_name(self):
        # Regression test: the display name isn't always present on
        # every message from a sender, an earlier message with a blank
        # name shouldn't blank out a name a later message actually has.
        messages = [
            msg("a@a.com", sender_name=""),
            msg("a@a.com", sender_name="Retailer Deals"),
        ]
        summaries = aggregate_by_sender(messages)
        self.assertEqual(summaries[0].sender_name, "Retailer Deals")

    def test_prefers_safe_to_automate_unsubscribe_when_mixed(self):
        messages = [
            msg("a@a.com", list_unsub="<https://a.com/unsub>"),  # not one-click
            msg(
                "a@a.com",
                list_unsub="<https://a.com/unsub>",
                list_unsub_post="List-Unsubscribe=One-Click",
            ),
        ]
        summaries = aggregate_by_sender(messages)
        self.assertTrue(summaries[0].unsubscribe.safe_to_automate)


if __name__ == "__main__":
    unittest.main()
