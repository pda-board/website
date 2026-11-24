#!/usr/bin/env python3
"""pdamail: email drafts for the TU/e Postdoc Association board.

Fills the templates in ./templates with data from events/events.json and the
contacts workbook, and writes previews (.html/.txt), calendar files (.ics) and
Outlook drafts (.eml). It never sends anything.

  python3 tools/mail/pdamail.py render announcement --event borrel-glow-walk-2026
  python3 tools/mail/pdamail.py draft announce --event borrel-glow-walk-2026 --test-to me@tue.nl
  python3 tools/mail/pdamail.py draft newsletter --intro intro.md --news news.json
  python3 tools/mail/pdamail.py draft welcome --to new.member@tue.nl --name "Alex"
  python3 tools/mail/pdamail.py contacts check ~/Documents/PDA/contacts.xlsx
  python3 tools/mail/pdamail.py ics --event borrel-glow-walk-2026

Needs Python 3.9+ and openpyxl (only for reading the contacts workbook).
"""

import argparse
import datetime as dt
import html
import json
import re
import subprocess
import sys
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr, formatdate
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TEMPLATES = HERE / "templates"
TZ = ZoneInfo("Europe/Amsterdam")

DEFAULT_CONFIG = {
    "sender_email": "postdoc_association@tue.nl",
    "sender_name": "TU/e Postdoc Association",
    "contacts_path": "~/Documents/PDA/contacts.xlsx",
    "contacts_sheet": "Contacts",
    "drafts_dir": "~/Documents/PDA/mail-drafts",
    "events_path": "events/events.json",
    "batch_size": 400,
    "unsubscribe_url": "",
    "site_base": "https://pda-tue.nl/",
    "ics_uid_domain": "pda-board.github.io",
    "newsletter_days_ahead": 120,
    "welcome_events": 3,
}

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
EMAIL_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
                      r"@([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$")
TOKEN_RE = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


class PdaMailError(Exception):
    pass


def warn(msg):
    print(f"  ! {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- config / data

def load_config(path=None):
    cfg = dict(DEFAULT_CONFIG)
    path = Path(path) if path else HERE / "config.json"
    if path.exists():
        cfg.update({k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")})
    if not cfg["site_base"].endswith("/"):
        cfg["site_base"] += "/"
    return cfg


def resolve(p):
    p = Path(p).expanduser()
    return p if p.is_absolute() else (REPO / p)


def outside_repo(path, what):
    """Contact data must never live inside the (public) website repository."""
    rp = Path(path).expanduser().resolve()
    try:
        rp.relative_to(REPO)
    except ValueError:
        return rp
    raise PdaMailError(f"{what} {rp} is inside the website repository, which is public. "
                       f"Keep contact data and drafts outside it (e.g. ~/Documents/PDA/).")


def load_events(cfg, path=None):
    p = resolve(path or cfg["events_path"])
    if not p.exists():
        raise PdaMailError(f"events file not found: {p} (use --events PATH)")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):  # tolerate {"events": [...]}
        data = data.get("events", [])
    return data


def find_event(events, event_id):
    for ev in events:
        if ev.get("id") == event_id:
            if ev.get("published") is False:
                warn(f"event '{event_id}' is not published on the website yet; links to its page will not work.")
            return ev
    ids = ", ".join(e.get("id", "?") for e in events)
    raise PdaMailError(f"no event with id '{event_id}'. Known ids: {ids}")


# --------------------------------------------------------------------------- dates

def parse_local(s):
    """'2026-11-10T17:30' (Europe/Amsterdam) -> aware datetime; '2026-11-10' -> date."""
    if not s:
        return None
    s = str(s).strip()
    if len(s) == 10:
        return dt.date.fromisoformat(s)
    d = dt.datetime.fromisoformat(s)
    return d.replace(tzinfo=TZ) if d.tzinfo is None else d.astimezone(TZ)


def as_date(d):
    return d.date() if isinstance(d, dt.datetime) else d


def date_long(d):
    d = as_date(d)
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def date_short(d):
    d = as_date(d)
    return f"{DAYS[d.weekday()][:3]} {d.day} {MONTHS[d.month - 1][:3]} {d.year}"


def event_times(ev):
    start, end = parse_local(ev.get("start")), parse_local(ev.get("end"))
    return start, end


def time_text(ev):
    if ev.get("time_label"):
        return ev["time_label"]
    start, end = event_times(ev)
    if not isinstance(start, dt.datetime):
        return "All day" if start else "Time to be announced"
    if isinstance(end, dt.datetime):
        if end.date() == start.date():
            return f"{start:%H:%M} – {end:%H:%M}"
        return f"{start:%H:%M} – {date_short(end)} {end:%H:%M}"
    return f"From {start:%H:%M}"


def date_text(ev, short=False):
    start, _ = event_times(ev)
    if start:
        return date_short(start) if short else date_long(start)
    return ev.get("date_label") or "Date to be announced"


def when_phrase(ev, today):
    start, _ = event_times(ev)
    if not start:
        return f"coming up ({ev.get('date_label') or 'date to be announced'})"
    days = (as_date(start) - today).days
    d = as_date(start)
    if days < 0:
        warn(f"event '{ev['id']}' is in the past ({d}).")
        return f"on {DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days < 7:
        return f"this {DAYS[d.weekday()]}"
    return f"on {DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def is_upcoming(ev, today):
    if ev.get("published") is False:
        return False
    start, end = event_times(ev)
    last = end or start
    return last is None or as_date(last) >= today


def sort_key(ev):
    start, _ = event_times(ev)
    return (start is None, as_date(start) if start else dt.date.max, ev.get("title", ""))


# --------------------------------------------------------------------------- text helpers

F = "font-family:Arial, Lato, Helvetica, sans-serif;"
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
BULLET_RE = re.compile(r"^\s*[-*]\s+")


def _inline_html(text):
    out, pos = [], 0
    for m in LINK_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()], quote=False))
        out.append(f'<a class="t-link" href="{html.escape(m.group(2))}" style="color:#C72125;">'
                   f'{html.escape(m.group(1), quote=False)}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:], quote=False))
    return BOLD_RE.sub(r"<strong>\1</strong>", "".join(out))


def _blocks(text):
    if isinstance(text, list):
        text = "\n\n".join(str(t) for t in text)
    text = (text or "").replace("\r\n", "\n").strip()
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def md_to_html(text, size=16, line=24):
    """Tiny Markdown subset: paragraphs, '- ' bullets, [text](url) links, **bold**."""
    p_style = f'class="t-ink" style="margin:0 0 16px 0; {F} font-size:{size}px; line-height:{line}px; color:#1A1A1F;"'
    ul_style = (f'class="t-ink" style="margin:0 0 16px 0; padding:0 0 0 22px; {F} '
                f'font-size:{size}px; line-height:{line}px; color:#1A1A1F;"')
    parts = []
    for block in _blocks(text):
        # split the block into runs of plain lines and runs of bullet lines
        runs = []
        for l in block.split("\n"):
            is_bullet = bool(BULLET_RE.match(l))
            if runs and runs[-1][0] == is_bullet:
                runs[-1][1].append(l)
            else:
                runs.append((is_bullet, [l]))
        for is_bullet, lines in runs:
            if is_bullet:
                items = "".join('<li style="margin:0 0 6px 0;">' + _inline_html(BULLET_RE.sub("", l)) + "</li>"
                                for l in lines)
                parts.append(f"<ul {ul_style}>{items}</ul>")
            else:
                parts.append(f"<p {p_style}>" + "<br>".join(_inline_html(l.strip()) for l in lines) + "</p>")
    return "\n    ".join(parts)


def md_to_text(text, indent=""):
    out = []
    for block in _blocks(text):
        b = LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", block)
        b = BOLD_RE.sub(r"\1", b)
        out.append("\n".join(indent + l.strip() for l in b.split("\n")))
    return "\n\n".join(out)


def first_sentence(text, limit=140):
    t = re.sub(r"\s+", " ", md_to_text(text)).strip()
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    t = m.group(1) if m else t
    return t if len(t) <= limit else t[:limit - 1].rsplit(" ", 1)[0] + "…"


def abs_url(cfg, path):
    if not path:
        return ""
    if re.match(r"^(https?:|mailto:)", path):
        return path
    return cfg["site_base"] + path.lstrip("/")


# --------------------------------------------------------------------------- templates

def load_template(name, kind):
    p = TEMPLATES / f"{name}.{kind}"
    if not p.exists():
        raise PdaMailError(f"template not found: {p}")
    t = p.read_text(encoding="utf-8")
    if kind == "html":  # drop the documentation comment
        t = re.sub(r"[ \t]*<!-- PDA-TEMPLATE.*?-->\n?", "", t, count=1, flags=re.S)
    return t


def fill(name, kind, tokens):
    """Plain string replacement, as Power Automate would do it.

    In HTML, values are escaped unless the token name ends in _html.
    """
    t = load_template(name, kind)
    missing = []

    def sub(m):
        key = m.group(1)
        if key not in tokens:
            missing.append(key)
            return m.group(0)
        val = "" if tokens[key] is None else str(tokens[key])
        if kind == "html" and not key.endswith("_html"):
            val = html.escape(val, quote=True)
        return val

    out = TOKEN_RE.sub(sub, t)
    if missing:
        raise PdaMailError(f"template {name}.{kind}: no value for {', '.join(sorted(set(missing)))}")
    if kind == "txt":
        out = re.sub(r"[ \t]+\n", "\n", out)
        out = re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"
    return out


def unsubscribe_url(cfg):
    return cfg.get("unsubscribe_url") or f"mailto:{cfg['sender_email']}?subject=Unsubscribe"


def event_tokens(ev, cfg):
    eid = ev["id"]
    start, _ = event_times(ev)
    event_url = abs_url(cfg, f"events/{eid}/")
    calendar_url = abs_url(cfg, f"cal/{eid}.ics") if start else event_url
    reg = ev.get("registration_url") or ""
    if reg:
        cta_url, cta_label = reg, "Register now"
    elif start:
        cta_url, cta_label = calendar_url, "Add to calendar"
    elif ev.get("external_url"):
        cta_url, cta_label = ev["external_url"], "More information"
    else:
        cta_url, cta_label = event_url, "Event details"
    price = (ev.get("price") or "").strip()
    if ev.get("registration_required") and reg:
        note = (f"{price}, but registration is mandatory." if price else "Registration is mandatory.")
        reminder = "Registration is mandatory. If you haven't signed up yet, please do it today."
    elif reg:
        note = "Please register, so we know how many people to expect."
        reminder = "If you haven't registered yet, there is still time."
    else:
        note = "No registration needed, just come along."
        reminder = "No registration needed, just come along."
    return {
        "event_id": eid,
        "event_title": ev.get("title", ""),
        "event_date": date_text(ev),
        "event_date_short": date_text(ev, short=True),
        "event_time": time_text(ev),
        "event_location": ev.get("location") or "To be announced",
        "event_price": price or "See the event page",
        "event_summary": ev.get("summary") or "",
        "event_url": event_url,
        "calendar_url": calendar_url,
        "cta_url": cta_url,
        "cta_label": cta_label,
        "registration_note": note,
        "reminder_note": reminder,
        "event_link_label": "Details and registration" if reg else "Details",
        "unsubscribe_url": unsubscribe_url(cfg),
    }


def programme_parts(ev):
    rows = [r for r in (ev.get("programme") or []) if (r.get("item") or "").strip()]
    if not rows:
        return "", ""
    tok = [{"programme_time": r.get("time") or "", "programme_item": r["item"]} for r in rows]
    rows_html = "".join(fill("event_programme_row", "html", t) for t in tok)
    rows_text = "".join(fill("event_programme_row", "txt", t) for t in tok)
    return (fill("event_programme", "html", {"programme_rows_html": rows_html}),
            fill("event_programme", "txt", {"programme_rows_text": rows_text}))


def flyer_html(ev, cfg):
    img = abs_url(cfg, ev.get("image"))
    if not img:
        return ""
    return fill("event_flyer", "html", {
        "flyer_image_url": img,
        "flyer_link_url": abs_url(cfg, ev.get("flyer_pdf")) or img,
        "event_title": ev.get("title", ""),
    })


def event_list_parts(events, cfg, empty_text):
    if not events:
        msg = html.escape(empty_text)
        return (f'      <tr><td class="t-muted bd" style="padding:14px 0; border-top:1px solid #E4E4E4; {F} '
                f'font-size:15px; line-height:22px; color:#636363;">{msg}</td></tr>', empty_text + "\n")
    toks = [event_tokens(e, cfg) for e in events]
    return ("".join(fill("newsletter_event_item", "html", t) for t in toks),
            "\n".join(fill("newsletter_event_item", "txt", t) for t in toks))


# --------------------------------------------------------------------------- calendar

def ics_escape(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line):
    """Fold to 75 octets per line (RFC 5545 3.1) without splitting UTF-8 characters."""
    out, cur, limit = [], b"", 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > limit:
            out.append(cur)
            cur, limit = b" ", 75
        cur += b
    out.append(cur)
    return b"\r\n".join(out).decode("utf-8")


def make_ics(ev, cfg, now=None):
    start, end = event_times(ev)
    if not start:
        raise PdaMailError(f"event '{ev['id']}' has no start date, so no calendar file can be made.")
    now = now or dt.datetime.now(dt.timezone.utc)
    utc = lambda d: d.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if isinstance(start, dt.datetime):
        if not isinstance(end, dt.datetime) or end <= start:
            if end is None:
                warn(f"event '{ev['id']}' has no end time; the calendar entry lasts 2 hours.")
            end = start + dt.timedelta(hours=2)
        when = [f"DTSTART:{utc(start)}", f"DTEND:{utc(end)}"]
    else:
        last = as_date(end) if end else start
        when = [f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
                f"DTEND;VALUE=DATE:{last + dt.timedelta(days=1):%Y%m%d}"]
    event_url = abs_url(cfg, f"events/{ev['id']}/")
    desc = md_to_text(ev.get("summary") or "")
    if ev.get("registration_url"):
        desc += ("\n\nRegistration is mandatory: " if ev.get("registration_required") else "\n\nRegister: ") \
            + ev["registration_url"]
    desc += f"\n\nDetails: {event_url}\nTU/e Postdoc Association"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//TU/e Postdoc Association//Website//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{ev['id']}@{cfg['ics_uid_domain']}",
        f"SEQUENCE:{int(ev.get('sequence') or ev.get('ics_sequence') or 0)}",
        f"DTSTAMP:{utc(now)}",
        *when,
        f"SUMMARY:{ics_escape(ev.get('title'))}",
        f"LOCATION:{ics_escape(ev.get('location'))}",
        f"DESCRIPTION:{ics_escape(desc.strip())}",
        f"URL:{event_url}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(ics_fold(l) for l in lines) + "\r\n"


# --------------------------------------------------------------------------- builders
# Each returns dict(subject, html, text, attachments=[(filename, bytes, maintype, subtype, params)])

def build_announcement(ev, cfg, args):
    t = event_tokens(ev, cfg)
    prog_h, prog_t = programme_parts(ev)
    t.update({
        "preheader": first_sentence(ev.get("summary") or "") or f"{t['event_date']}, {t['event_location']}",
        "event_description_html": md_to_html(ev.get("description") or ""),
        "event_description_text": md_to_text(ev.get("description") or ""),
        "programme_html": prog_h, "programme_text": prog_t,
        "flyer_html": flyer_html(ev, cfg),
    })
    if not event_times(ev)[0]:
        warn("event has no start date: the 'Add to calendar' link points to the event page instead.")
    subject = args.subject or f"New PDA event: {t['event_title']} ({t['event_date_short']})"
    return {"subject": subject, "html": fill("event_announcement", "html", t),
            "text": fill("event_announcement", "txt", t), "attachments": ics_attachment(ev, cfg)}


def build_reminder(ev, cfg, args):
    t = event_tokens(ev, cfg)
    t["event_when_phrase"] = when_phrase(ev, args.today)
    t["preheader"] = f"{t['event_date']}, {t['event_time']} at {t['event_location']}"
    subject = args.subject or f"Reminder: {t['event_title']} is {t['event_when_phrase']}"
    return {"subject": subject, "html": fill("event_reminder", "html", t),
            "text": fill("event_reminder", "txt", t), "attachments": ics_attachment(ev, cfg)}


def ics_attachment(ev, cfg):
    if not event_times(ev)[0]:
        return []
    data = make_ics(ev, cfg).encode("utf-8")
    return [(f"{ev['id']}.ics", data, "text", "calendar", {"method": "PUBLISH", "charset": "utf-8"})]


def upcoming(events, today, days=None):
    ev = [e for e in events if is_upcoming(e, today)]
    if days:
        horizon = today + dt.timedelta(days=days)
        ev = [e for e in ev if not event_times(e)[0] or as_date(event_times(e)[0]) <= horizon]
    return sorted(ev, key=sort_key)


def build_newsletter(events, cfg, args):
    today = args.today
    if args.intro:
        intro = Path(args.intro).expanduser().read_text(encoding="utf-8")
    else:
        warn("no --intro file given; using a short placeholder intro for this preview.")
        intro = "Hi all,\n\nHere is what's coming up for postdocs at TU/e this month."
    news = []
    if args.news:
        news = json.loads(Path(args.news).expanduser().read_text(encoding="utf-8"))
        if isinstance(news, dict):
            news = news.get("news", [])
    ev = upcoming(events, today, cfg["newsletter_days_ahead"])
    ev_h, ev_t = event_list_parts(ev, cfg, "No events scheduled right now. We will let you know as soon as there is something new.")
    news_h = news_t = ""
    if news:
        items = [{"news_title": n.get("title", ""),
                  "news_body_html": md_to_html(n.get("body", ""), 15, 22),
                  "news_body_text": md_to_text(n.get("body", ""), indent="  "),
                  "news_link": abs_url(cfg, n.get("link")) or cfg["site_base"]} for n in news]
        news_h = fill("newsletter_news_section", "html",
                      {"news_items_html": "".join(fill("newsletter_news_item", "html", i) for i in items)})
        news_t = fill("newsletter_news_section", "txt",
                      {"news_items_text": "\n".join(fill("newsletter_news_item", "txt", i) for i in items)})
    title = args.title or f"{MONTHS[today.month - 1]} {today.year}"
    t = {"newsletter_title": title, "preheader": first_sentence(intro.split("\n\n", 1)[-1]),
         "intro_html": md_to_html(intro), "intro_text": md_to_text(intro),
         "events_html": ev_h, "events_text": ev_t, "news_html": news_h, "news_text": news_t,
         "unsubscribe_url": unsubscribe_url(cfg)}
    subject = args.subject or f"PDA newsletter, {title}"
    return {"subject": subject, "html": fill("newsletter", "html", t),
            "text": fill("newsletter", "txt", t), "attachments": []}


def build_welcome(events, cfg, args):
    name = (args.name or "").strip().split(" ")[0] or "there"
    ev = upcoming(events, args.today)[: cfg["welcome_events"]]
    ev_h, ev_t = event_list_parts(ev, cfg, "Nothing scheduled right now. We will email you about the next event.")
    t = {"first_name": name, "preheader": "What the PDA does, what's coming up, and where to find us.",
         "events_html": ev_h, "events_text": ev_t, "unsubscribe_url": unsubscribe_url(cfg)}
    subject = args.subject or "Welcome to the TU/e Postdoc Association"
    return {"subject": subject, "html": fill("welcome_member", "html", t),
            "text": fill("welcome_member", "txt", t), "attachments": []}


def check_rendered(msg):
    for part in ("html", "text"):
        left = re.findall(r"\{\{[^}]*\}\}", msg[part])
        if left:
            raise PdaMailError(f"unfilled placeholders in {part}: {sorted(set(left))}")


# --------------------------------------------------------------------------- contacts

def normalise_email(v):
    s = str(v or "").replace("\u00a0", " ").strip()
    s = re.sub(r"^mailto:", "", s, flags=re.I).strip().strip("<>").strip()
    return s.lower()


def read_contacts(path, sheet="Contacts"):
    try:
        import openpyxl
    except ImportError:
        raise PdaMailError("openpyxl is missing. Install it with:  python3 -m pip install --user openpyxl")
    path = outside_repo(path, "contacts file")
    if not path.exists():
        raise PdaMailError(f"contacts file not found: {path} (set contacts_path in config.json or use --contacts)")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        raise PdaMailError(f"no sheet '{sheet}' in {path.name}; sheets: {', '.join(wb.sheetnames)}")
    rows = wb[sheet].iter_rows(values_only=True)
    header, header_row = None, 0
    for i, row in enumerate(rows, start=1):
        names = [str(c or "").strip().lower() for c in row]
        if "email" in names:
            header, header_row = names, i
            break
    if not header:
        raise PdaMailError(f"no header row with an 'Email' column in sheet '{sheet}'")
    col = {n: header.index(n) for n in header if n}

    def get(row, name):
        j = col.get(name)
        return row[j] if j is not None and j < len(row) else None

    rep = {"rows": 0, "active": [], "unsubscribed": [], "other_status": [], "invalid": [],
           "duplicates": [], "blank": 0, "first_seen": {}, "missing_columns":
           [c for c in ("email", "first name", "last name", "status") if c not in col]}
    by_email = {}
    for i, row in enumerate(rows, start=header_row + 1):
        if row is None or all(c in (None, "") for c in row):
            continue
        rep["rows"] += 1
        raw = get(row, "email")
        email = normalise_email(raw)
        status = str(get(row, "status") or "").strip().lower()
        if not email:
            rep["blank"] += 1
            continue
        if not EMAIL_RE.match(email) or ".." in email:
            rep["invalid"].append((i, str(raw)))
            continue
        if email in by_email:
            rep["duplicates"].append((i, email, by_email[email]["row"]))
            # an unsubscribe anywhere wins
            if status == "unsubscribed":
                by_email[email]["status"] = "unsubscribed"
            continue
        by_email[email] = {"row": i, "email": email, "status": status,
                           "first": str(get(row, "first name") or "").strip(),
                           "last": str(get(row, "last name") or "").strip()}
    for c in by_email.values():
        if c["status"] in ("", "active"):
            rep["active"].append(c)
        elif c["status"] == "unsubscribed":
            rep["unsubscribed"].append(c)
        else:
            rep["other_status"].append(c)
    return rep


def print_contacts_report(rep, verbose=True):
    print(f"Rows with data:        {rep['rows']}")
    print(f"Will receive mail:     {len(rep['active'])}  (Status = Active or empty)")
    print(f"Unsubscribed:          {len(rep['unsubscribed'])}")
    if rep["other_status"]:
        sts = sorted({c['status'] for c in rep['other_status']})
        print(f"Other status, skipped: {len(rep['other_status'])}  ({', '.join(sts)})")
    print(f"Duplicate rows:        {len(rep['duplicates'])}  (same address again; only the first is used)")
    print(f"Invalid addresses:     {len(rep['invalid'])}")
    print(f"Rows without email:    {rep['blank']}")
    if rep["missing_columns"]:
        print(f"Missing columns:       {', '.join(rep['missing_columns'])}")
    if verbose:
        doms = {}
        for c in rep["active"]:
            d = c["email"].split("@")[1]
            doms[d] = doms.get(d, 0) + 1
        top = sorted(doms.items(), key=lambda x: -x[1])[:5]
        if top:
            print("Domains (active):      " + ", ".join(f"{d} {n}" for d, n in top))
        if rep["invalid"]:
            print("\nInvalid addresses (row: value):")
            for r, v in rep["invalid"]:
                print(f"  row {r}: {v!r}")
        if rep["duplicates"]:
            print("\nDuplicates (row: address, first seen in row):")
            for r, e, first in rep["duplicates"][:50]:
                print(f"  row {r}: {e} (row {first})")
            if len(rep["duplicates"]) > 50:
                print(f"  ... and {len(rep['duplicates']) - 50} more")


# --------------------------------------------------------------------------- .eml

def make_eml(msg, cfg, to, bcc=()):
    m = EmailMessage(policy=SMTP)
    m["From"] = formataddr((cfg["sender_name"], cfg["sender_email"]))
    m["To"] = to
    if bcc:
        m["Bcc"] = ", ".join(bcc)
    m["Subject"] = msg["subject"]
    m["Date"] = formatdate(localtime=True)
    m["X-Unsent"] = "1"  # Outlook opens the file as an editable draft
    m.set_content(msg["text"], subtype="plain", charset="utf-8")
    m.add_alternative(msg["html"], subtype="html", charset="utf-8")
    for fname, data, maintype, subtype, params in msg["attachments"]:
        m.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname, params=params)
    return m.as_bytes()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


# --------------------------------------------------------------------------- commands

KIND_ALIASES = {"announce": "announcement", "announcement": "announcement", "event_announcement": "announcement",
                "reminder": "reminder", "event_reminder": "reminder",
                "newsletter": "newsletter", "welcome": "welcome", "welcome_member": "welcome"}


def build(kind, cfg, args):
    events = load_events(cfg, args.events)
    if kind in ("announcement", "reminder"):
        if not args.event:
            raise PdaMailError(f"{kind} needs --event ID")
        ev = find_event(events, args.event)
        msg = (build_announcement if kind == "announcement" else build_reminder)(ev, cfg, args)
    elif kind == "newsletter":
        msg = build_newsletter(events, cfg, args)
    else:
        msg = build_welcome(events, cfg, args)
    check_rendered(msg)
    return msg


def cmd_render(cfg, args):
    kinds = ["announcement", "reminder", "newsletter", "welcome"] if args.template == "all" \
        else [KIND_ALIASES.get(args.template) or sys.exit(f"unknown template {args.template}")]
    out = Path(args.out).expanduser() if args.out else HERE / "out"
    out.mkdir(parents=True, exist_ok=True)
    for kind in kinds:
        if kind in ("announcement", "reminder") and not args.event:
            print(f"skip {kind}: needs --event")
            continue
        msg = build(kind, cfg, args)
        stem = f"{kind}-{args.event}" if kind in ("announcement", "reminder") else kind
        (out / f"{stem}.html").write_text(msg["html"], encoding="utf-8")
        (out / f"{stem}.txt").write_text(msg["text"], encoding="utf-8")
        written = [f"{stem}.html", f"{stem}.txt"]
        for fname, data, *_ in msg["attachments"]:
            (out / fname).write_bytes(data)
            written.append(fname)
        print(f"{kind:13s} subject: {msg['subject']}")
        print(f"{'':13s} wrote:   {', '.join(str(out / w) for w in written)}")


def cmd_draft(cfg, args):
    kind = KIND_ALIASES[args.kind]
    if kind == "newsletter" and not args.intro:
        raise PdaMailError("draft newsletter needs --intro FILE.md (the text written by the board)")
    msg = build(kind, cfg, args)
    out = Path(args.out).expanduser() if args.out else Path(cfg["drafts_dir"]).expanduser()
    outside_repo(out, "drafts folder")
    stamp = args.today.isoformat()
    tag = args.event or (slug(args.to or "") if kind == "welcome" else "")
    run_dir = out / "-".join(x for x in (stamp, args.kind, tag) if x)
    run_dir.mkdir(parents=True, exist_ok=True)
    files = []
    if kind == "welcome":
        if not args.to:
            raise PdaMailError("draft welcome needs --to EMAIL")
        to = args.test_to or args.to
        if not EMAIL_RE.match(normalise_email(to)):
            raise PdaMailError(f"not a valid email address: {to}")
        if args.test_to:
            msg["subject"] = "[TEST] " + msg["subject"]
        f = run_dir / f"{stamp}-welcome-{slug(args.to)}.eml"
        f.write_bytes(make_eml(msg, cfg, to))
        files.append(f)
        print(f"Welcome draft for {args.to}" + (f" (test copy to {args.test_to})" if args.test_to else ""))
    elif args.test_to:
        msg["subject"] = "[TEST] " + msg["subject"]
        f = run_dir / f"{stamp}-{args.kind}-TEST.eml"
        f.write_bytes(make_eml(msg, cfg, args.test_to))
        files.append(f)
        print(f"Test draft: To = {args.test_to}, no BCC recipients.")
    else:
        rep = read_contacts(args.contacts or cfg["contacts_path"], cfg["contacts_sheet"])
        emails = [c["email"] for c in rep["active"]]
        if not emails:
            raise PdaMailError("no active contacts found; nothing to draft.")
        size = max(1, int(args.batch_size or cfg["batch_size"]))
        batches = [emails[i:i + size] for i in range(0, len(emails), size)]
        for n, batch in enumerate(batches, start=1):
            f = run_dir / f"{stamp}-{args.kind}-{n:02d}of{len(batches):02d}.eml"
            f.write_bytes(make_eml(msg, cfg, cfg["sender_email"], batch))
            files.append(f)
        print(f"Recipients: {len(emails)} (in BCC), {len(batches)} draft(s) of at most {size}.")
        print(f"Skipped:    {len(rep['unsubscribed'])} unsubscribed, {len(rep['other_status'])} other status, "
              f"{len(rep['invalid'])} invalid, {len(rep['duplicates'])} duplicate rows, {rep['blank']} without email.")
        if rep["invalid"]:
            print("            (run 'contacts check' to see which rows)")
    print(f"Subject:    {msg['subject']}")
    if msg["attachments"]:
        print(f"Attached:   {', '.join(a[0] for a in msg['attachments'])}")
    for f in files:
        print(f"  {f}")
    if args.open:
        if sys.platform != "darwin":
            print("--open only works on macOS; open the .eml files by hand.")
        else:
            for f in files:
                subprocess.run(["open", str(f)], check=False)


def cmd_contacts(cfg, args):
    rep = read_contacts(args.file or cfg["contacts_path"], args.sheet or cfg["contacts_sheet"])
    print_contacts_report(rep)


def cmd_ics(cfg, args):
    ev = find_event(load_events(cfg, args.events), args.event)
    data = make_ics(ev, cfg)
    out = Path(args.out).expanduser() if args.out else HERE / "out"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{ev['id']}.ics"
    f.write_bytes(data.encode("utf-8"))
    print(f)


def main(argv=None):
    p = argparse.ArgumentParser(prog="pdamail", description="Email drafts for the TU/e PDA board. Never sends mail.")
    p.add_argument("--config", help="config file (default: tools/mail/config.json)")
    p.add_argument("--events", help="events.json (default from config)")
    p.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today(),
                   help="pretend today is YYYY-MM-DD (for previews)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--event", help="event id from events.json")
        sp.add_argument("--intro", help="newsletter intro, a small Markdown file")
        sp.add_argument("--news", help="newsletter news items, JSON list of {title, body, link}")
        sp.add_argument("--title", help="newsletter title (default: current month)")
        sp.add_argument("--name", help="first name for the welcome email")
        sp.add_argument("--subject", help="override the subject line")
        sp.add_argument("--out", help="output folder")
        sp.add_argument("--events", default=argparse.SUPPRESS, help="events.json (default from config)")
        sp.add_argument("--today", type=dt.date.fromisoformat, default=argparse.SUPPRESS,
                        help="pretend today is YYYY-MM-DD (for previews)")

    r = sub.add_parser("render", help="write .html/.txt previews")
    r.add_argument("template", help="announcement | reminder | newsletter | welcome | all")
    common(r)

    d = sub.add_parser("draft", help="write Outlook drafts (.eml)")
    d.add_argument("kind", choices=["announce", "reminder", "newsletter", "welcome"])
    common(d)
    d.add_argument("--to", help="welcome: the new member's address")
    d.add_argument("--contacts", help="contacts .xlsx (default from config)")
    d.add_argument("--batch-size", type=int, help="max BCC recipients per draft (default from config)")
    d.add_argument("--test-to", help="make one draft addressed only to this address")
    d.add_argument("--open", action="store_true", help="open the drafts in Outlook (macOS)")

    c = sub.add_parser("contacts", help="check the contacts workbook")
    c.add_argument("action", choices=["check"])
    c.add_argument("file", nargs="?", help="contacts .xlsx (default from config)")
    c.add_argument("--sheet", help="sheet name (default: Contacts)")

    i = sub.add_parser("ics", help="write the calendar file for an event")
    i.add_argument("--event", required=True)
    i.add_argument("--out")
    i.add_argument("--events", default=argparse.SUPPRESS)

    args = p.parse_args(argv)
    cfg = load_config(args.config)
    try:
        {"render": cmd_render, "draft": cmd_draft, "contacts": cmd_contacts, "ics": cmd_ics}[args.cmd](cfg, args)
    except PdaMailError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
