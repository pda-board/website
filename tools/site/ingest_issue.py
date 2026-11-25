#!/usr/bin/env python3
"""Add or update an event in events/events.json from a GitHub issue body.

The issue body must contain one fenced ```json block holding a single event
object with the events.json schema. "id" is optional: without it the id is the
slugified title plus the year (e.g. "Borrel & GLOW Walk" in 2026 ->
"borrel-glow-walk-2026"). Missing optional fields get their defaults. An
existing event with the same id is updated (fields in the issue replace the
stored ones; "sequence" is never taken from the issue).

    python3 tools/site/ingest_issue.py issue.md            # body from a file
    ISSUE_BODY="..." python3 tools/site/ingest_issue.py    # body from the environment
    python3 tools/site/ingest_issue.py --events /tmp/events.json issue.md

Exit status 0 on success (prints the event URL), 1 on a parse or validation
error (prints the reason). With --github-output FILE it also appends id=, url=,
action= lines for GitHub Actions, and with --error-file FILE it writes the error
message there.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

FENCE_RE = re.compile(r"```[ \t]*json[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S | re.I)
# Sent by the Power Automate flows through GitHub's reply-by-email: base64 survives
# the line wrapping and quote mangling that email clients apply to plain JSON.
B64_RE = re.compile(r"PDA-EVENT-BEGIN\s+([A-Za-z0-9+/=\s]+?)\s*PDA-EVENT-END")
ACTIONS = ("add", "update", "cancel", "restore", "remove")


class IngestError(Exception):
    pass


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("&", " ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def event_year(ev: dict) -> str:
    if isinstance(ev.get("start"), str) and re.match(r"^\d{4}", ev["start"]):
        return ev["start"][:4]
    label = ev.get("date_label")
    m = re.search(r"\b(\d{4})\b", label) if isinstance(label, str) else None
    if m:
        return m.group(1)
    return str(dt.date.today().year)


def parse_body(body: str) -> dict:
    b64 = B64_RE.findall(body or "")
    if b64:
        try:
            blocks = [base64.b64decode(re.sub(r"\s+", "", b64[0]), validate=True).decode("utf-8")]
        except (binascii.Error, UnicodeDecodeError):
            raise IngestError("The PDA-EVENT block is not valid base64.")
    else:
        blocks = FENCE_RE.findall(body or "")
    if not blocks:
        raise IngestError("No ```json block found in the issue. Paste the event as a JSON object "
                          "between a line with ```json and a line with ```.")
    if len(blocks) > 1:
        raise IngestError("Found %d ```json blocks; put exactly one event per issue." % len(blocks))
    try:
        ev = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise IngestError("The ```json block is not valid JSON: %s (line %d, column %d)."
                          % (exc.msg, exc.lineno, exc.colno))
    if not isinstance(ev, dict):
        raise IngestError("The ```json block must contain one event object ({...}), not a list.")
    ev.pop("sequence", None)
    action = ev.get("action", "add")
    if action not in ACTIONS:
        raise IngestError("Unknown action %r; use one of %s." % (action, ", ".join(ACTIONS)))
    if action != "add":
        return ev
    ev.pop("action", None)
    if ev.get("id") and isinstance(ev["id"], str) and not build.ID_RE.match(ev["id"]):
        # e.g. an id built by the Power Automate flow from a title with odd characters
        ev["id"] = slugify(ev["id"])
    if not ev.get("id"):
        if not isinstance(ev.get("title"), str) or not ev["title"].strip():
            raise IngestError("The event needs a 'title' (or an explicit 'id').")
        year = event_year(ev)
        slug = slugify(ev["title"])
        ev["id"] = slug if slug.endswith(year) else "%s-%s" % (slug, year)
    return ev


def day(ev: dict):
    s = ev.get("start")
    return s[:10] if isinstance(s, str) and len(s) >= 10 else None


def resolve_id(events: list, ev: dict) -> None:
    """Two different events can share a title in the same year (a monthly
    borrel, say). If an event with this id exists on ANOTHER day, this is a new
    event: add the date to its id instead of overwriting the old one."""
    old = next((e for e in events if e.get("id") == ev["id"]), None)
    if old and day(ev) and day(old) and day(ev) != day(old):
        ev["id"] = "%s-%s" % (ev["id"], day(ev)[5:].replace("-", ""))  # e.g. borrel-2026-1210


def upsert(events: list, ev: dict):
    """Return (new_events, action). Keeps the schema field order."""
    for i, old in enumerate(events):
        if old.get("id") == ev["id"]:
            merged = dict(old)
            merged.update(ev)
            out = list(events)
            out[i] = ordered(merged)
            return out, "updated"
    full = dict(build.DEFAULTS)
    full.update(ev)
    return events + [ordered(full)], "added"


def ordered(ev: dict) -> dict:
    out = {k: ev[k] for k in build.FIELDS if k in ev}
    out.update({k: v for k, v in ev.items() if k not in out})  # unknown keys: validation reports them
    return out


def find_event(events: list, ref) -> dict:
    """An event by id, by the link to its page, or by its exact title (case and spaces ignored)."""
    if not isinstance(ref, str) or not ref.strip():
        raise IngestError("Say which event: paste the link to its page, or its exact title.")
    ref = ref.strip()
    m = re.search(r"/events/([a-z0-9-]+)", ref)
    key = m.group(1) if m else ref
    hit = [e for e in events if e.get("id") == key]
    if not hit:
        norm = lambda s: re.sub(r"\s+", " ", (s or "").strip().lower())
        hit = [e for e in events if norm(e.get("title")) == norm(ref)]
        if len(hit) > 1:  # same title in several years: take the latest
            hit = sorted(hit, key=lambda e: e.get("start") or "", reverse=True)[:1]
    if not hit:
        raise IngestError("No event matches %r. Paste the link to the event page instead." % ref)
    return hit[0]


def change(events: list, cmd: dict):
    """Apply an update/cancel/restore/remove command. Returns (events, id, action)."""
    action = cmd.pop("action")
    target = find_event(events, cmd.pop("event", None) or cmd.get("id"))
    cmd.pop("id", None)
    new = dict(target)
    if action == "update":
        fields = {k: v for k, v in cmd.items() if k in build.FIELDS and v not in (None, "", [])}
        if not fields:
            raise IngestError("Nothing to change: fill in at least one field.")
        new.update(fields)
    elif action == "cancel":
        new["cancelled"] = True
    elif action == "restore":
        new["cancelled"], new["published"] = False, True
    elif action == "remove":
        new["published"] = False
    out = [ordered(new) if e is target else e for e in events]
    return out, new["id"], {"update": "updated", "cancel": "cancelled", "restore": "restored", "remove": "removed"}[action]


def ingest(body: str, events_path: Path):
    ev = parse_body(body)
    try:
        events = json.loads(events_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestError("Cannot read %s: %s" % (events_path, exc))
    if ev.get("action", "add") != "add":
        new, eid, action = change(events, ev)
        errors = build.validate(new)
        if errors:
            raise IngestError("The change does not pass validation:\n- " + "\n- ".join(errors))
        events_path.write_text(build.dump_events(new), encoding="utf-8")
        return eid, action
    resolve_id(events, ev)
    new, action = upsert(events, ev)
    errors = build.validate(new)
    if errors:
        raise IngestError("The event does not pass validation:\n- " + "\n- ".join(errors))
    events_path.write_text(build.dump_events(new), encoding="utf-8")
    return ev["id"], action


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Add/update an event in events.json from an issue body.")
    ap.add_argument("body_file", nargs="?", help="file with the issue body (default: $ISSUE_BODY)")
    ap.add_argument("--events", default=str(build.EVENTS_JSON), help="events.json to update")
    ap.add_argument("--github-output", help="append id/url/action to this file (GitHub Actions)")
    ap.add_argument("--error-file", help="write the error message to this file on failure")
    args = ap.parse_args(argv)
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else os.environ.get("ISSUE_BODY", "")
    try:
        eid, action = ingest(body, Path(args.events))
    except IngestError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        if args.error_file:
            Path(args.error_file).write_text(str(exc) + "\n", encoding="utf-8")
        return 1
    url = build.SITE + "events/%s/" % eid
    print("%s %s: %s" % (action.capitalize(), eid, url))
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write("id=%s\nurl=%s\naction=%s\n" % (eid, url, action))
    return 0


if __name__ == "__main__":
    sys.exit(main())
