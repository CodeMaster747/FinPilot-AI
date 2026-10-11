"""schema.org JSON-LD extraction, shared by the email parser (Order markup) and the product crawler."""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup


def extract_jsonld(markup: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(markup, "lxml")
    objects: list[dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = tag.string or tag.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        _flatten(data, objects)
    return objects


def _flatten(data: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(data, list):
        for item in data:
            _flatten(item, out)
    elif isinstance(data, dict):
        if "@graph" in data:
            _flatten(data["@graph"], out)
        if "@type" in data:
            out.append(data)


def of_type(objects: list[dict[str, Any]], type_name: str) -> list[dict[str, Any]]:
    found = []
    for obj in objects:
        t = obj.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(isinstance(x, str) and x.split("/")[-1] == type_name for x in types):
            found.append(obj)
    return found
