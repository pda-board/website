# PDA mail tools

Ready-made emails for the PDA board: event announcements, reminders, the newsletter and the welcome email for new members. The script fills in the templates and prepares **Outlook drafts**. It never sends anything: you open a draft, check it, and press Send.

> This folder is part of a **public** website repository. Never put the contacts list, drafts or anyone's email address in it. Keep them in `~/Documents/PDA/` (the default).

## One-time setup

1. Download the contacts workbook from the PDA Board Teams files and save it as `~/Documents/PDA/contacts.xlsx`
   (or change `contacts_path` in `config.json`). It needs a sheet called **Contacts** with the columns
   Email, First name, Last name, Department, Source, Added on, Status. Only rows with Status **Active** (or empty) get mail.
2. Check that Python can read Excel files:
   `python3 -c "import openpyxl"`. If that prints an error, run `python3 -m pip install --user openpyxl`.
3. When the unsubscribe Microsoft Form exists, put its link in `unsubscribe_url` in `config.json`.
   Until then the "Unsubscribe" link opens an email to postdoc_association@tue.nl with subject "Unsubscribe".

All commands below are run from the website folder (`cd ~/tue-pda-website`).

## Everyday use

**Check the contacts list** (counts, duplicates, broken addresses, with row numbers so you can fix them in Excel):

    python3 tools/mail/pdamail.py contacts check ~/Documents/PDA/contacts.xlsx

**Announce a new event.** The event must be in `events/events.json` (its `id` is the last part of the event page address).

    python3 tools/mail/pdamail.py draft announce --event borrel-glow-walk-2026 --test-to you@tue.nl --open
    python3 tools/mail/pdamail.py draft announce --event borrel-glow-walk-2026 --open

Always make a test draft first (`--test-to`), send it to yourself and look at it on your laptop and phone.
The real run puts everyone in **BCC**, in batches of 400 (Exchange allows at most 500 recipients per message),
so you get one draft per batch and send each one. The calendar file (.ics) is attached so people can add the event to Outlook in one click.

**Reminder a few days before:**

    python3 tools/mail/pdamail.py draft reminder --event talking-science-2026 --open

**Newsletter.** Write the intro in a small text file (blank line between paragraphs, `- ` for bullets,
`[link text](https://...)` for links, `**bold**`). Upcoming events from the website are added automatically.
News items are optional, in a JSON file: `[{"title": "...", "body": "...", "link": "https://..."}]`.

    python3 tools/mail/pdamail.py draft newsletter --intro ~/Documents/PDA/newsletter-dec.md --news ~/Documents/PDA/news-dec.json --title "December 2026" --open

**Welcome a new member** (one personal email, not BCC):

    python3 tools/mail/pdamail.py draft welcome --to new.person@tue.nl --name "Alex" --open

**Only look, no drafts:** `render` writes an .html and .txt preview to `tools/mail/out/` (ignored by git):

    python3 tools/mail/pdamail.py render all --event borrel-glow-walk-2026 --intro intro.md

Useful options: `--subject "..."` to change the subject, `--batch-size 250`, `--out FOLDER`,
`--contacts FILE.xlsx`, `--events FILE.json`, `--today 2026-11-03` (pretend it is another day, for previews).

### Notes on the drafts

- Drafts are saved in `~/Documents/PDA/mail-drafts/<date>-<kind>-<event>/`. `--open` opens them in Outlook (macOS).
- The `.eml` files carry `X-Unsent: 1`, so classic Outlook for Mac opens them as an editable draft.
  If your Outlook opens one read-only (some versions of the "new Outlook" do), use the legacy Outlook, or open the file and choose *Forward / Edit as new*.
- From is postdoc_association@tue.nl. To send from the shared mailbox you need *Send As* rights on it;
  check the From field before sending. To is the shared mailbox itself, so a copy lands there.
- People who unsubscribe: set their Status to `Unsubscribed` in the workbook (do not delete the row, so they are not re-added later).
  If the same address appears twice and one row says Unsubscribed, they get no mail.

## Using these templates in Power Automate

Every template is a complete HTML file with simple `{{token}}` placeholders, so a flow can fill it with plain
**replace()** expressions, e.g. `replace(replace(variables('html'), '{{event_title}}', triggerBody()?['title']), ...)`.
No loops or conditions live inside a template. Where something repeats (events, news, programme lines),
there is a separate small "block" template: fill one block per item and join them into the parent's `*_html` token.
A `*_html` token may be left empty (replace it with `''`); every other token must be filled.
Escape `&`, `<` and `>` in plain-text values (`&` becomes `&amp;`), also inside URLs. Each HTML template starts with a comment that lists its tokens;
the comment is invisible in the email. Each `.txt` file is the plain-text version with the same tokens (`*_text` instead of `*_html`).

Fixed in every template: logo, colours, footer with postdoc_association@tue.nl, the website, LinkedIn and Instagram.
Every main template has `{{unsubscribe_url}}` (the Microsoft Form link, or `mailto:postdoc_association@tue.nl?subject=Unsubscribe`).

| Template | Tokens |
|---|---|
| `event_announcement` | preheader, event_title, event_date, event_time, event_location, event_price, event_summary, registration_note, cta_url, cta_label, event_url, calendar_url, unsubscribe_url; HTML parts: event_description_html, programme_html, flyer_html (text: event_description_text, programme_text) |
| `event_programme` (block → programme_html) | programme_rows_html (text: programme_rows_text) |
| `event_programme_row` (repeat) | programme_time, programme_item |
| `event_flyer` (block → flyer_html) | flyer_image_url, flyer_link_url, event_title |
| `event_reminder` | preheader, event_title, event_date, event_time, event_when_phrase, event_location, reminder_note, cta_url, cta_label, event_url, calendar_url, unsubscribe_url |
| `newsletter` | preheader, newsletter_title, unsubscribe_url; HTML parts: intro_html, events_html, news_html (text: intro_text, events_text, news_text) |
| `newsletter_event_item` (repeat → events_html) | event_date_short, event_time, event_title, event_location, event_summary, event_url, event_link_label |
| `newsletter_news_section` (block → news_html) | news_items_html (text: news_items_text) |
| `newsletter_news_item` (repeat) | news_title, news_body_html, news_link (text: news_body_text) |
| `welcome_member` | preheader, first_name, unsubscribe_url; HTML part: events_html (newsletter_event_item blocks; text: events_text) |

Values the script uses, so a flow can match them:

- `event_date` "Tuesday 10 November 2026", `event_date_short` "Tue 10 Nov 2026", `event_time` "17:30 – 20:00"
  (or the event's `time_label`). Events without a start use `date_label`.
- `event_url` `https://pda-tue.nl/events/<id>/`, `calendar_url` `https://pda-tue.nl/cal/<id>.ics`.
- `cta_url`/`cta_label`: the registration form and "Register now" if there is one, otherwise the calendar file and "Add to calendar".
- `event_when_phrase`: "today", "tomorrow", "this Friday" (within a week), otherwise "on Friday 11 December".

Calendar files: `pdamail.py ics --event <id>` writes the same `.ics` that is attached to the drafts
(METHOD:PUBLISH, times converted from Europe/Amsterdam to UTC, UID `<id>@pda-board.github.io`, as on the website).
If you change an event that people already have in their calendar, add `"sequence": 1` (then 2, ...) to the event in `events.json`
so Outlook replaces the old entry instead of adding a second one.
