#!/usr/bin/env python3
"""Write the email templates used by the Power Automate flows into the
"Templates" table of the PDA contacts workbook.

The flows (see tools/mail/README.md, "Power Automate") read one row per
template from that table and fill the remaining {{tokens}} with replace().
This script pre-fills what the flows do not need to vary (unsubscribe link,
empty optional blocks) so each flow only replaces a handful of tokens.

    python3 tools/mail/flow_templates.py --print          # print the rows

Then paste the Html cells into the ONLINE workbook by hand. Never upload a
locally edited copy over the live workbook: the flows add contacts to it all
the time (they would be lost) and recreating the table can change its id,
which breaks the flows.
"""
import re
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

HERE = Path(__file__).resolve().parent / "templates"
UNSUB = "mailto:postdoc_association@tue.nl?subject=Unsubscribe"


def load(name):
    t = (HERE / name).read_text(encoding="utf-8")
    return re.sub(r"<!-- PDA-TEMPLATE.*?-->\n?", "", t, flags=re.S)


def fill(t, **kw):
    for k, v in kw.items():
        t = t.replace("{{%s}}" % k, v)
    return t


def rows():
    welcome = load("welcome_member.html")
    welcome = re.sub(r'(>Coming up</h2>)\s*<table role="presentation"[^>]*>\s*\{\{events_html\}\}\s*</table>',
                     r"\1", welcome).replace(">Coming up</h2>", ">What's on</h2>")
    welcome = fill(welcome, preheader="Welcome to the PDA: what to expect and how to reach us.",
                   unsubscribe_url=UNSUB)

    announcement = fill(load("event_announcement.html"), preheader="{{event_summary}}",
                        programme_html="", flyer_html="", unsubscribe_url=UNSUB)

    newsletter = fill(load("newsletter.html"), preheader="PDA newsletter: {{newsletter_title}}",
                      unsubscribe_url=UNSUB)

    news_block = fill(load("newsletter_news_section.html"),
                      news_items_html=fill(load("newsletter_news_item.html"),
                                           news_title="Also from the PDA", news_link="https://pda-tue.nl/"))

    return [
        ("welcome", "Welcome to the TU/e Postdoc Association", welcome),
        ("announcement", "{{event_title}}: {{event_date}}", announcement),
        ("newsletter", "PDA newsletter: {{newsletter_title}}", newsletter),
        ("newsletter_event_item", "", load("newsletter_event_item.html")),
        ("news_block", "", news_block),
    ]


def main(path):
    wb = load_workbook(path)
    if "Templates" in wb.sheetnames:
        del wb["Templates"]
    s = wb.create_sheet("Templates")
    s.append(["Name", "Subject", "Html"])
    for name, subject, html in rows():
        assert len(html) < 32000, name
        s.append([name, subject, html])
    t = Table(displayName="Templates", ref="A1:C%d" % (s.max_row))
    t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    s.add_table(t)
    s.column_dimensions["A"].width = 22
    s.column_dimensions["B"].width = 40
    s.column_dimensions["C"].width = 60
    wb.save(path)
    for name, subject, html in rows():
        print("%-22s %6d chars  tokens: %s" % (name, len(html), sorted(set(re.findall(r"\{\{(\w+)\}\}", html)))))


if __name__ == "__main__":
    if sys.argv[1:] == ["--print"]:
        for name, subject, html_ in rows():
            print("=== %s | %s\n%s\n" % (name, subject, html_))
    else:
        main(sys.argv[1])  # writes a LOCAL workbook copy only
