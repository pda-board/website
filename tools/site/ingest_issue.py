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


class IngestError(Exception):
    pass


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("&", " ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def event_year(ev: dict) -> str:
    if isinstance(ev.get("start"), str) and re.match(r"^\d{4}", ev["start"]):
        return ev["start"][:4]
    m = re.search(r"\b(\d{4})\b", ev.get("date_label") or "")
    if m:
        return m.group(1)
    return str(dt.date.today().year)


def parse_body(body: str) -> dict:
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
    if not ev.get("id"):
        if not isinstance(ev.get("title"), str) or not ev["title"].strip():
            raise IngestError("The event needs a 'title' (or an explicit 'id').")
        year = event_year(ev)
        slug = slugify(ev["title"])
        ev["id"] = slug if slug.endswith(year) else "%s-%s" % (slug, year)
    return ev


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


def ingest(body: str, events_path: Path):
    ev = parse_body(body)
    try:
        events = json.loads(events_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestError("Cannot read %s: %s" % (events_path, exc))
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
