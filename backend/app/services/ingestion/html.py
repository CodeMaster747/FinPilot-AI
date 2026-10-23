"""Readable text from email HTML (bank alerts and receipts are often HTML-only)."""

from __future__ import annotations

import re

BLOCK_TAGS = ["p", "div", "table", "tr", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "section", "header", "footer",
              "article", "blockquote", "pre", "hr", "title"]


def html_to_text(markup: str) -> str:
    """Line breaks only at block elements, so "<b>₹649</b>" stays inside its sentence, and each table row on one line
    with its cells separated by spaces."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(markup, "lxml")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for cell in soup.find_all(["td", "th"]):
        cell.insert_after(" ")
    for block in soup.find_all(BLOCK_TAGS):
        block.insert_before("\n")
        block.insert_after("\n")
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in soup.get_text("").splitlines()]
    return "\n".join(ln for ln in lines if ln)
