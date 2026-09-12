# inboxsweep

Points an IMAP connection at your inbox and tells you which senders are
actually cluttering it: how many messages they've sent, whether they
offer a real unsubscribe link, and whether that link looks like the
kind you can safely click. It doesn't touch anything unless you tell it
to.

Everyone has the same problem: a handful of senders account for most of
the mail nobody reads, and finding them by scrolling through an inbox
one message at a time is exactly the kind of chore people put off
indefinitely. This scans the headers, ranks the senders by how much
they've cluttered things up, and only acts when you explicitly say so.

No third-party dependencies. `imaplib` and `email` are both in the
Python standard library, so there's nothing to install beyond Python
itself.

## Why it doesn't just click "unsubscribe" for you

Clicking an unsubscribe link in a spam or phishing email is a known way
to make things worse: it confirms to whoever sent it that your address
is live and someone's reading it, which is worth more to a spammer than
silence. A legitimate mailing list, the kind built on Mailchimp,
SendGrid, or a retailer's own ESP, follows a standard called RFC 8058
that makes unsubscribing a real one-click action with no confirmation
page and no way to abuse it as a tracking pixel. inboxsweep checks for
that standard specifically and only calls a sender "safe to
unsubscribe" when it's present. Everything else gets reported, not
acted on, so you can look at it yourself before doing anything.

## Install

```
git clone https://github.com/rakshit-gen/inboxsweep.git
cd inboxsweep
pip install .
```

## Credentials

inboxsweep reads connection details from environment variables, never
from a config file it writes itself, and it never stores your password
anywhere:

```
export INBOXSWEEP_HOST=imap.gmail.com
export INBOXSWEEP_USER=you@gmail.com
export INBOXSWEEP_PASS=your-app-specific-password
```

Use an app-specific password, not your real account password, if your
provider offers one (Gmail, Outlook, and most others do). That way a
leaked environment variable doesn't hand over the whole account.

## Usage

See who's cluttering your inbox:

```
inboxsweep scan --since 90d
```

This only fetches headers, not message bodies, and uses `BODY.PEEK[HEADER]`
specifically so scanning never marks anything as read.

Hide senders that only show up once or twice, since those are rarely
the ones worth acting on:

```
inboxsweep scan --since 90d --min-count 5
```

Archive everything from a sender once you've decided it's junk:

```
inboxsweep archive --sender newsletter@example.com --apply
```

Leaving off `--apply` prints what it would do without doing it, which
is the default, so `archive` and `delete` are both safe to run without
the flag:

```
inboxsweep archive --sender newsletter@example.com
inboxsweep delete --sender spammy@example.com --apply
```

## Example

```
$ inboxsweep scan --since 90d
Sender                               Count  Unsubscribe
deals@retailer.com                      42  one-click, verified safe: https://retailer.com/unsub?id=abc
news@blog.com                           18  mailto only, verify manually: mailto:unsub@blog.com
friend@example.com                       3  no unsubscribe link found
```

`deals@retailer.com` is the only one inboxsweep would ever call "safe":
a real https unsubscribe link plus the RFC 8058 one-click header. The
blog's mailto-based unsubscribe still shows up, but nothing here clicks
it or sends that email for you.

## License

MIT
