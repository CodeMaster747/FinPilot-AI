"""Reads the current price of a product from a link the user pasted into their wishlist.

Polite and honest by design: robots.txt is respected, the request identifies itself, one page is fetched per check,
and links to private or local addresses are refused (the server runs on the user's network). The price comes from
markup that stores publish for search engines — schema.org Product/Offer JSON-LD, Open Graph / product meta tags,
or microdata — so no per-store scraping rules are needed. Many large stores block automated requests or render
prices with JavaScript; then the user enters the price by hand.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from protego import Protego

from app.services.jsonld import extract_jsonld, of_type

USER_AGENT = "FinPilotPriceCheck/2.0 (personal wishlist price check; one page per day)"
MAX_REDIRECTS = 5
TIMEOUT = 12.0
MAX_BYTES = 3 * 1024 * 1024


@dataclass
class PriceResult:
    status: str  # ok | no_price | robots | blocked | error | not_inr | invalid
    note: str = ""
    price: Decimal | None = None
    title: str | None = None
    image: str | None = None
    store: str | None = None
    url: str | None = None


def store_name(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return host


def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


def validate_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Paste a full product link starting with https://")
    if len(url) > 1000:
        raise ValueError("That link is too long.")
    return url


def _amount(value: object) -> Decimal | None:
    if value is None:
        return None
    text = re.sub(r"[^\d.]", "", str(value).replace(",", ""))
    if not text or text.count(".") > 1:
        return None
    try:
        price = Decimal(text)
    except InvalidOperation:
        return None
    return price if price > 0 else None


def _offer_price(offers: object) -> tuple[Decimal | None, str | None]:
    items = offers if isinstance(offers, list) else [offers]
    best: tuple[Decimal | None, str | None] = (None, None)
    for off in items:
        if not isinstance(off, dict):
            continue
        price = _amount(off.get("price") or off.get("lowPrice"))
        spec = off.get("priceSpecification")
        if price is None and isinstance(spec, dict):
            price = _amount(spec.get("price"))
        currency = off.get("priceCurrency") or (spec.get("priceCurrency") if isinstance(spec, dict) else None)
        if price is not None and (best[0] is None or price < best[0]):
            best = (price, currency)
    return best


def parse_price(html: str, base_url: str = "") -> PriceResult:
    """Price, title and image from a product page's structured markup."""
    title = image = None
    price: Decimal | None = None
    currency: str | None = None
    for product in of_type(extract_jsonld(html), "Product"):
        title = title or product.get("name")
        img = product.get("image")
        image = image or (img[0] if isinstance(img, list) and img else img if isinstance(img, str) else
                          img.get("url") if isinstance(img, dict) else None)
        p, c = _offer_price(product.get("offers"))
        if p is not None:
            price, currency = p, c
            break
    soup = BeautifulSoup(html, "lxml")

    def meta(*names: str) -> str | None:
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    if price is None:
        price = _amount(meta("product:price:amount", "og:price:amount"))
        currency = meta("product:price:currency", "og:price:currency") or currency
    if price is None:
        tag = soup.find(attrs={"itemprop": "price"})
        if tag is not None:
            price = _amount(tag.get("content") or tag.get_text())
            cur = soup.find(attrs={"itemprop": "priceCurrency"})
            currency = (cur.get("content") if cur else None) or currency
    title = title or meta("og:title", "twitter:title") or (soup.title.get_text(strip=True) if soup.title else None)
    image = image or meta("og:image", "twitter:image")
    if image and base_url:
        image = urljoin(base_url, image)
    if price is None:
        return PriceResult("no_price", "This page doesn't publish its price in a form FinPilot can read.", title=title, image=image)
    if currency and currency.upper() not in ("INR", "RS", "₹"):
        return PriceResult("not_inr", f"The page lists the price in {currency}, not rupees.", title=title, image=image)
    return PriceResult("ok", "", price=price.quantize(Decimal("0.01")), title=title, image=image)


class _PrivateRedirect(Exception):
    pass


def _get(client: httpx.Client, url: str, check_hosts: bool) -> httpx.Response:
    """GET, following redirects one hop at a time, so a redirect to a private or local address is refused before
    anything is requested from it (httpx's automatic redirects would only let us check the final address afterwards)."""
    for _ in range(MAX_REDIRECTS + 1):
        res = client.get(url, follow_redirects=False)
        if not res.is_redirect:
            return res
        nxt = urljoin(str(res.url), res.headers.get("location", ""))
        parsed = urlparse(nxt)
        if parsed.scheme not in ("http", "https") or (check_hosts and not _public_host(parsed.hostname or "")):
            raise _PrivateRedirect(nxt)
        url = nxt
    raise httpx.TooManyRedirects("Too many redirects", request=res.request)


def _robots_allows(client: httpx.Client, url: str, check_hosts: bool = False) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        res = _get(client, robots_url, check_hosts)
    except (httpx.HTTPError, _PrivateRedirect):
        return True  # no robots.txt reachable: nothing disallows us (the page itself is checked the same way)
    if res.status_code >= 400:
        return True
    return Protego.parse(res.text).can_fetch(url, USER_AGENT)


def fetch_price(url: str, client: httpx.Client | None = None) -> PriceResult:
    try:
        url = validate_url(url)
    except ValueError as exc:
        return PriceResult("invalid", str(exc), url=url)
    host = urlparse(url).hostname or ""
    store = store_name(url)
    own_client = client is None
    if client is None:
        if not _public_host(host):
            return PriceResult("invalid", "That link points to a private or local address.", store=store, url=url)
        client = httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers={
            "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-IN,en;q=0.8"})
    try:
        if not _robots_allows(client, url, own_client):
            return PriceResult("robots", f"{store} asks automated tools not to read this page (robots.txt). Enter the price yourself.",
                               store=store, url=url)
        res = _get(client, url, own_client)
        if res.status_code in (401, 403, 429, 503):
            return PriceResult("blocked", f"{store} didn't let FinPilot read the page (it blocks automated requests). "
                                          "Enter the price yourself.", store=store, url=url)
        if res.status_code >= 400:
            return PriceResult("error", f"{store} answered with an error ({res.status_code}). Check the link.", store=store, url=url)
        html = res.text[:MAX_BYTES]
    except _PrivateRedirect:
        return PriceResult("invalid", "That link redirects to a private or local address.", store=store, url=url)
    except httpx.HTTPError as exc:
        return PriceResult("error", f"Couldn't open the link ({exc.__class__.__name__}). Check the laptop's internet connection.",
                           store=store, url=url)
    finally:
        if own_client:
            client.close()
    result = parse_price(html, str(res.url))
    result.store, result.url = store, url
    return result
