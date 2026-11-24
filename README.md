# TU/e Postdoc Association — website

Website of the TU/e Postdoc Association (PDA). Hand-written static HTML (no
framework). Events come from `events/events.json`: a small Python script turns
them into the event lists, event pages and calendar files, and the generated
files are committed, so the hosts serve the repository as-is.

## What is in it

- **Hero** with the PDA mission and a "next event" card
- **About**: the three pillars (Connect / Grow / Be heard) and the mission quote from tue.nl
- **Next event** spotlight (navy, `#next-event`) and **Events**: upcoming / past tabs,
  with a link to the all-events page `events/`
- **Best Paper Award** feature band (facts from the 2026 edition on tue.nl)
- **Board**: the eight current board members, with photos
- **Join**: perks, and a button to the membership form on tue.nl
- **Resources**: onboarding, career & funding, wellbeing
- **Footer / contact**: email, LinkedIn group, Instagram, PostdocNL

- **Event pages** `events/<id>/`: one per event, with details, flyer, Register,
  add-to-calendar and Share buttons, and their own link-preview tags

The logo (`img/logo*.png`, plus `favicon.png` and the link-preview image `og-card.png`) is the PDA logo from tue.nl. Calendar files for events live in `cal/`.

Palette and type follow the TU/e house style (red `#C72125`, navy `#0E2470`,
Lato body). Urbanist stands in for Gilroy (TU/e's heading font, which is not
freely licensed). Dark mode follows the visitor's system setting.

## Board photos

Photos live in `img/board/` as 480×480 JPEGs, named after the person
(`firstname-lastname.jpg`). Most come from the TU/e research portal; Femke
Verheggen's is from her LinkedIn profile.

## Events

All events live in **`events/events.json`**; never edit the event rows, the hero
"Next up" card, the `#next-event` spotlight, `events/**/index.html` or `cal/*.ics`
by hand. To add or change an event, either:

1. **Edit `events/events.json`** and push to `main`. The *Events* GitHub Action
   (`.github/workflows/events.yml`) runs the build and commits the generated
   files. You can also build locally first:

   ```sh
   python3 tools/site/build.py          # rebuild (safe to run any time)
   python3 tools/site/build.py --check  # only validate events.json
   python3 -m http.server               # preview at http://localhost:8000/
   ```

2. **Open a GitHub issue with the label `new-event`** whose body contains one
   event as a fenced ```` ```json ```` block (same fields as below; `id` may be
   left out). The Action adds it (or updates the event with the same `id`),
   builds, pushes, comments with the event link and closes the issue. If the
   JSON is wrong it comments the error and leaves the issue open: edit the issue
   body and it is processed again. The parser is `tools/site/ingest_issue.py`
   and can be run locally on a file: `python3 tools/site/ingest_issue.py body.md`.
   A Power Automate flow can create such issues through the GitHub connector.

The Action also runs daily, so events move from Upcoming to Past on their own.

### Event fields

| field | |
|---|---|
| `id` | slug, unique; also the page folder (`events/<id>/`) and calendar UID (`<id>@pda-board.github.io`). Don't change it once published. |
| `title`, `summary` | `summary` is 1–2 sentences, used in the lists, link previews, emails and calendars |
| `type` | `social`, `career`, `workshop`, `talk`, `award` or `other`: colours the first chip |
| `tags` | chips; the first one gets the type colour (e.g. `["Pitch competition", "Free"]`). Empty: the type name |
| `start`, `end` | Amsterdam local time `2026-11-10T17:30`, or `null` if the date is not known yet |
| `date_label` | used when `start` is `null`: `"TBA Dec 2026"`, `"Dec 2021"`, `"15 Jun 2026"` |
| `time_label` | optional text instead of the computed time, e.g. `"From 17:30"` |
| `location`, `location_url` | |
| `description` | longer text; blank lines separate paragraphs; `[text](url)` links |
| `programme` | `[{"time": "17:30", "item": "Borrel"}]` |
| `registration_url`, `registration_required`, `price` | Register buttons and "Free, but registration is mandatory." |
| `image`, `flyer_pdf` | site-relative paths, e.g. `img/flyers/glow-walk-2026.jpg` (the image is also the link-preview picture) |
| `external_url` | "Details on tue.nl" style link |
| `featured` | `true`: this event drives the hero card and the spotlight while it is upcoming. Otherwise the next dated upcoming event does |
| `past_cta` | `{"label": "About the award", "href": "#award"}`: button shown once the event is past (default: its event page) |
| `published` | `false` hides the event and removes its page |
| `sequence` | calendar SEQUENCE; managed by the build (bumped when the calendar content changes), also read by the mail tool |

An event is "upcoming" until the day of its `end` (or `start`, or the last day
of its `date_label`) has passed.

### Sharing

Every upcoming event row, the spotlight and every event page have a **Share**
menu. The shared link is always `https://pda-tue.nl/events/<id>/`, whose preview
(WhatsApp, LinkedIn, Teams) shows the event title, summary and flyer.

- **Email via Outlook** opens a new Outlook on the web message with a ready-made
  text (title, date, place, summary, register link, event link); **Other email
  app** does the same through `mailto:`.
- **WhatsApp** and **LinkedIn** use their share links.
- **More apps** (phones and browsers that support it) opens the system share
  sheet, which is the way to Instagram; **Copy link** copies the event link and
  **Download image** saves the flyer for a story or post.
- **Add to Outlook calendar**, a Google Calendar link and the `.ics` file.

Without JavaScript the menu still opens and all options except Copy link and
More apps work. The script is `js/share.js`; all styling is in `css/site.css`.

Flyer QR codes point to `.../website/#next-event`, which always shows the
featured (or next) event.

## Flyers

Each flyer is an HTML page in `flyers/` (e.g. `flyers/glow-walk-2026.html`),
rendered with headless Chrome:

```sh
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# 300 dpi A4 image (2481 x 3509); turn it into the print PDF with any image-to-PDF tool
"$CHROME" --headless=new --hide-scrollbars --allow-file-access-from-files \
  --force-device-scale-factor=3.125 --virtual-time-budget=8000 --window-size=794,1123 \
  --screenshot=flyer.png flyers/glow-walk-2026.html
```

Print the PDF built from that image rather than Chrome's own "print to PDF":
the neon glows do not survive as vectors. Web copies live in `img/flyers/`.

## Where the site is published

- **https://pda-tue.nl/** is the main address. It is deployed from this repository
  (`https://github.com/pda-board/website`, branch `main`, root) through the
  university subdomain service. Pushing to `main` updates it.
- **https://pda-board.github.io/website/** (GitHub Pages, same branch) stays on:
  the 2026 GLOW Walk flyer's QR code points there.

## Editing

The page content is plain HTML in `index.html`: edit it freely outside the
`<!-- BUILD:… START -->` / `<!-- BUILD:… END -->` markers (what is between them
is rewritten by `tools/site/build.py`). Styling for all pages is in
`css/site.css`, with colours defined once as CSS variables in `:root`. All
in-site links are relative, because the site is served both from the domain
root (pda-tue.nl) and from a subpath (pda-board.github.io/website/).
