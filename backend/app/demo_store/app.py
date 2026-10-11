"""Bundled demo storefronts: real websites (HTML + schema.org JSON-LD + sitemaps + robots.txt) that the
Smart Picks crawler visits. Served on a second port by the same process; nothing here touches the app DB."""

from __future__ import annotations

import html
import json
from datetime import date

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.core.money import fmt_inr
from app.demo_store.catalog import SHOPS, by_shop, find, find_sku, in_stock, on_sale, price_on

CSS = """
body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;margin:0;background:#f7f7f5;color:#1a1a19}
header{background:#fff;border-bottom:1px solid #e5e4de;padding:16px 24px}
header a{color:inherit;text-decoration:none;font-weight:700;font-size:20px}
main{max-width:1080px;margin:0 auto;padding:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}
.card{background:#fff;border:1px solid #e5e4de;border-radius:12px;padding:12px;text-decoration:none;color:inherit;display:block}
.card img{width:100%;border-radius:8px}
.price{font-weight:700;font-size:18px}.mrp{color:#898781;text-decoration:line-through;margin-left:6px;font-size:13px}
.sale{display:inline-block;background:#e8f5ec;color:#006300;border-radius:6px;padding:2px 6px;font-size:12px;margin-top:4px}
.note{background:#fff8e6;border:1px solid #f0d58a;border-radius:8px;padding:10px 14px;margin-bottom:16px;font-size:14px}
"""


def page(title: str, body: str, shop: str | None = None) -> HTMLResponse:
    brand = SHOPS[shop]["name"] if shop else "FinPilot demo stores"
    home = f"/{shop}/" if shop else "/"
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><header><a href='{home}'>{html.escape(brand)}</a></header>"
        f"<main>{body}</main></body></html>")


def create_store_app() -> FastAPI:
    app = FastAPI(title="FinPilot demo stores", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        cards = "".join(f"<a class='card' href='/{k}/'><h3>{v['name']}</h3><p>{v['tagline']}</p><p>{len(by_shop(k))} products</p></a>"
                        for k, v in SHOPS.items())
        note = ("<div class='note'>These storefronts are bundled with FinPilot AI so the Smart Picks crawler can be demonstrated "
                "offline. Products and brands are fictional; prices change daily on a fixed schedule.</div>")
        return page("FinPilot demo stores", note + f"<div class='grid'>{cards}</div>")

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots(request: Request) -> str:
        base = str(request.base_url).rstrip("/")
        return ("User-agent: *\nCrawl-delay: 0.15\nDisallow: /blockedmart/\nDisallow: /*/cart\nDisallow: /*/account\n\n"
                f"Sitemap: {base}/sitemap.xml\n")

    @app.get("/sitemap.xml")
    def sitemap_index(request: Request) -> Response:
        base = str(request.base_url).rstrip("/")
        entries = "".join(f"<sitemap><loc>{base}/{k}/sitemap.xml</loc></sitemap>" for k in SHOPS)
        return Response(f"<?xml version='1.0' encoding='UTF-8'?><sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>{entries}</sitemapindex>",
                        media_type="application/xml")

    @app.get("/{shop}/sitemap.xml")
    def shop_sitemap(shop: str, request: Request) -> Response:
        if shop not in SHOPS:
            raise HTTPException(404)
        base = str(request.base_url).rstrip("/")
        today = date.today().isoformat()
        urls = "".join(f"<url><loc>{base}/{shop}/p/{i.slug}/</loc><lastmod>{today}</lastmod></url>" for i in by_shop(shop))
        return Response(f"<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>{urls}</urlset>",
                        media_type="application/xml")

    @app.get("/{shop}/", response_class=HTMLResponse)
    def shop_home(shop: str) -> HTMLResponse:
        if shop not in SHOPS:
            raise HTTPException(404)
        today = date.today()
        cards = []
        for i in by_shop(shop):
            p = price_on(i, today)
            sale = "<div class='sale'>On sale</div>" if on_sale(i, today) else ""
            cards.append(f"<a class='card' href='/{shop}/p/{i.slug}/'><img src='/img/{i.sku}.svg' alt=''><div>{html.escape(i.title)}</div>"
                         f"<div><span class='price'>{fmt_inr(p)}</span><span class='mrp'>{fmt_inr(i.mrp)}</span></div>{sale}</a>")
        return page(SHOPS[shop]["name"], f"<h2>{SHOPS[shop]['tagline']}</h2><div class='grid'>{''.join(cards)}</div>", shop)

    @app.get("/{shop}/p/{slug}/", response_class=HTMLResponse)
    def product(shop: str, slug: str, request: Request) -> HTMLResponse:
        item = find(shop, slug)
        if item is None:
            raise HTTPException(404)
        today = date.today()
        base = str(request.base_url).rstrip("/")
        p = price_on(item, today)
        ld = {
            "@context": "https://schema.org", "@type": "Product", "name": item.title, "sku": item.sku,
            "brand": {"@type": "Brand", "name": item.brand}, "category": f"{item.category} > {item.product_type}",
            "description": item.description, "image": f"{base}/img/{item.sku}.svg", "keywords": ", ".join(item.tags),
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": item.rating, "reviewCount": item.rating_count},
            "offers": {"@type": "Offer", "url": f"{base}/{shop}/p/{slug}/", "priceCurrency": "INR", "price": f"{p:.2f}",
                       "availability": "https://schema.org/InStock" if in_stock(item, today) else "https://schema.org/OutOfStock",
                       "priceSpecification": {"@type": "UnitPriceSpecification", "price": f"{item.mrp:.2f}", "priceCurrency": "INR",
                                              "priceType": "https://schema.org/ListPrice"}},
        }
        body = (f"<script type='application/ld+json'>{json.dumps(ld)}</script>"
                f"<div style='display:grid;grid-template-columns:minmax(0,320px) 1fr;gap:24px'>"
                f"<img src='/img/{item.sku}.svg' alt='' style='width:100%;border-radius:12px'>"
                f"<div><h1>{html.escape(item.title)}</h1><p>{html.escape(item.description)}</p>"
                f"<p><span class='price'>{fmt_inr(p)}</span><span class='mrp'>{fmt_inr(item.mrp)}</span></p>"
                f"<p>{item.rating}★ · {item.rating_count:,} ratings</p><p><a href='/{shop}/cart'>Add to cart</a></p></div></div>")
        return page(item.title, body, shop)

    @app.get("/{shop}/cart", response_class=HTMLResponse)
    def cart(shop: str) -> HTMLResponse:
        return page("Cart", "<p>This is a demo store — nothing can be bought here.</p>", shop if shop in SHOPS else None)

    @app.get("/img/{sku}.svg")
    def image(sku: str) -> Response:
        item = find_sku(sku.upper())
        if item is None:
            raise HTTPException(404)
        hue = SHOPS[item.shop]["hue"]
        initials = "".join(w[0] for w in item.product_type.split()[:2]).upper()
        svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
               f"<stop offset='0' stop-color='hsl({hue},55%,92%)'/><stop offset='1' stop-color='hsl({hue},45%,80%)'/></linearGradient></defs>"
               f"<rect width='400' height='400' rx='32' fill='url(#g)'/>"
               f"<circle cx='200' cy='170' r='92' fill='hsl({hue},45%,42%)' opacity='0.92'/>"
               f"<text x='200' y='193' font-family='system-ui,sans-serif' font-size='64' font-weight='700' text-anchor='middle' fill='#fff'>{initials}</text>"
               f"<text x='200' y='318' font-family='system-ui,sans-serif' font-size='26' font-weight='600' text-anchor='middle' fill='hsl({hue},40%,22%)'>{html.escape(item.brand)}</text>"
               f"<text x='200' y='352' font-family='system-ui,sans-serif' font-size='18' text-anchor='middle' fill='hsl({hue},30%,30%)'>{html.escape(item.product_type)}</text></svg>")
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

    return app
