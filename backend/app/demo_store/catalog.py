"""Deterministic catalogue for the bundled demo storefronts (fictional brands, INR prices).

Prices follow a daily schedule — a small wobble plus rotating sales — so every crawl observes real price
changes. ``price_on(sku, day)`` is also what backfills 90 days of history on first boot.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

SHOPS = {
    "techkart": {"name": "TechKart", "tagline": "Gadgets, audio and computers", "hue": 215},
    "fitstop": {"name": "FitStop", "tagline": "Running, training and outdoor gear", "hue": 150},
    "homenest": {"name": "HomeNest", "tagline": "Kitchen, home and travel", "hue": 28},
    "dailycart": {"name": "DailyCart", "tagline": "Groceries and everyday essentials", "hue": 95},
    "blockedmart": {"name": "BlockedMart", "tagline": "This store disallows crawlers in robots.txt", "hue": 0},
}

# shop, category, product type, model names, brands, price range, tags
FAMILIES: list[tuple[str, str, str, list[str], list[str], tuple[int, int], list[str]]] = [
    ("techkart", "Electronics", "Noise-cancelling headphones", ["ANC 300 Wireless Headphones", "Studio ANC Pro Headphones", "Quiet Over-Ear ANC Headphones", "AirShell ANC Headphones"],
     ["Sonix", "AudioPeak", "Bassline"], (4999, 24999), ["headphones", "noise cancelling", "anc", "audio", "music"]),
    ("techkart", "Electronics", "Wireless earbuds", ["Buds Lite TWS Earbuds", "Buds Pro ANC Earbuds", "Sport Fit Earbuds"], ["Sonix", "Pulse", "Bassline"],
     (1299, 9999), ["earbuds", "audio", "music", "wireless"]),
    ("techkart", "Electronics", "Bluetooth speaker", ["Boom Mini Speaker", "Party 40W Speaker", "Shower Splash Speaker"], ["AudioPeak", "Pulse"],
     (999, 7999), ["speaker", "audio", "music"]),
    ("techkart", "Electronics", "Smartwatch", ["Fit Watch 2", "Active GPS Watch", "Runner Watch Pro"], ["Pulse", "Vertex"],
     (2499, 18999), ["smartwatch", "fitness tracker", "running", "gps"]),
    ("techkart", "Electronics", "Laptop", ["14 Laptop (i5, 16GB, 512GB)", "Book 15 Laptop (Ryzen 7, 16GB, 1TB)", "Slim 13 Laptop (i7, 16GB, 1TB)",
                                            "15 Creator Laptop (RTX 4050)", "Book 14 Lite Laptop (i3, 8GB, 512GB)"],
     ["Aero", "Zenix", "Lumen"], (34990, 98990), ["laptop", "notebook", "ultrabook", "computer"]),
    ("techkart", "Electronics", "Computer accessories", ["Mechanical Keyboard TKL", "Wireless Silent Mouse", "27-inch IPS Monitor", "USB-C 8-in-1 Hub",
                                                         "Laptop Cooling Pad"], ["Vertex", "Keyron"], (699, 17999), ["keyboard", "mouse", "monitor", "computer", "desk"]),
    ("techkart", "Electronics", "Phone accessories", ["65W GaN Fast Charger", "20000mAh Power Bank", "MagGrip Car Mount", "Braided USB-C Cable 2m"],
     ["Voltix", "Pulse"], (299, 3999), ["charger", "power bank", "phone", "cable"]),
    ("techkart", "Electronics", "Gaming", ["Wireless Game Controller", "RGB Gaming Headset", "Gaming Mouse 26K DPI"], ["Keyron", "Vertex"],
     (1499, 6999), ["gaming", "controller", "headset"]),
    ("fitstop", "Sports & Fitness", "Running shoes", ["Run 200 Running Shoes", "CloudStep Daily Trainer Running Shoes", "Tempo Race Running Shoes",
                                                       "TrailGrip Trail Running Shoes", "Run Lite Running Shoes"],
     ["Stride", "Kinetic", "Trailhead"], (1999, 11999), ["running shoes", "shoes", "running", "sneakers"]),
    ("fitstop", "Sports & Fitness", "Running apparel", ["Dry-Fit Running T-Shirt", "Running Shorts 2-in-1", "Reflective Running Jacket",
                                                         "Compression Running Tights"], ["Stride", "Kinetic"], (499, 3499), ["running", "apparel", "sportswear"]),
    ("fitstop", "Sports & Fitness", "Yoga & mobility", ["Yoga Mat 6mm", "Cork Yoga Block Set", "Foam Roller 45cm", "Yoga Mat 8mm Premium"],
     ["Asana", "Kinetic"], (399, 2999), ["yoga", "mat", "fitness", "mobility"]),
    ("fitstop", "Sports & Fitness", "Strength training", ["Hex Dumbbell Pair 5kg", "Adjustable Dumbbell 20kg", "Resistance Band Set", "Kettlebell 12kg",
                                                          "Pull-up Bar Doorway"], ["IronCore", "Kinetic"], (499, 12999), ["dumbbell", "strength", "gym", "fitness"]),
    ("fitstop", "Sports & Fitness", "Cycling", ["Cycling Helmet", "Bike Light Set", "Hybrid Bicycle 21-speed"], ["Velo", "Trailhead"],
     (799, 21999), ["cycling", "bicycle", "outdoor"]),
    ("fitstop", "Sports & Fitness", "Sports nutrition", ["Whey Protein 1kg (Chocolate)", "Whey Protein 2kg (Vanilla)", "Electrolyte Drink Mix 30 Sachets"],
     ["ProFuel", "NutriMax"], (649, 4499), ["whey protein", "protein", "nutrition", "supplement"]),
    ("homenest", "Home & Kitchen", "Air fryer", ["Air Fryer 4.2L Digital", "Air Fryer 6L Dual Basket", "Compact Air Fryer 2.5L"], ["Kitchora", "Homely"],
     (2999, 12999), ["air fryer", "kitchen", "appliance", "cooking"]),
    ("homenest", "Home & Kitchen", "Kitchen appliances", ["Mixer Grinder 750W", "Electric Kettle 1.7L", "Induction Cooktop 2000W", "Hand Blender 400W",
                                                          "Coffee Maker Drip 10-cup"], ["Kitchora", "Homely"], (999, 7999), ["kitchen", "appliance", "coffee", "cooking"]),
    ("homenest", "Home & Kitchen", "Cookware", ["Non-stick Cookware Set (3 pc)", "Cast Iron Skillet 26cm", "Pressure Cooker 5L"], ["Homely", "Kitchora"],
     (899, 4999), ["cookware", "kitchen", "cooking"]),
    ("homenest", "Home & Kitchen", "Home", ["Robot Vacuum Cleaner", "Cotton Bedsheet Set King", "LED Desk Lamp", "Air Purifier HEPA"], ["Homely", "CleanWave"],
     (799, 19999), ["home", "vacuum", "bedding", "lamp"]),
    ("homenest", "Travel", "Luggage", ["Cabin Trolley Bag 55cm", "Check-in Trolley 68cm", "Travel Backpack 40L", "Packing Cubes Set"],
     ["Roamer", "Voyago"], (899, 8999), ["luggage", "travel", "trip", "backpack"]),
    ("dailycart", "Groceries", "Coffee", ["Arabica Coffee Beans 250g", "Filter Coffee Powder 500g", "Cold Brew Coffee Bags (10)"], ["HillBean", "Kaapi Co"],
     (299, 899), ["coffee", "beans", "groceries"]),
    ("dailycart", "Groceries", "Health foods", ["Rolled Oats 1kg", "Mixed Nuts 500g", "Peanut Butter Crunchy 1kg", "Green Tea 100 Bags"],
     ["NutriMax", "Farmly"], (199, 1199), ["oats", "nuts", "healthy", "groceries", "tea"]),
    ("dailycart", "Groceries", "Sports nutrition", ["Whey Protein 1kg (Chocolate)", "Whey Protein 1kg (Cafe Mocha)"], ["ProFuel", "NutriMax"],
     (1799, 2599), ["whey protein", "protein", "nutrition", "supplement"]),
    ("dailycart", "Personal Care", "Grooming", ["Beard Trimmer Cordless", "Electric Toothbrush", "Sunscreen SPF 50 (100ml)"], ["Groomr", "Glow"],
     (349, 2999), ["grooming", "personal care", "trimmer"]),
    ("blockedmart", "Electronics", "Noise-cancelling headphones", ["Mega ANC Headphones"], ["Cheapo"], (1999, 3999), ["headphones", "anc"]),
    ("blockedmart", "Sports & Fitness", "Running shoes", ["Bargain Running Shoes"], ["Cheapo"], (799, 1499), ["running shoes"]),
    # appended last so the shared RNG leaves every earlier product unchanged
    ("techkart", "Electronics", "Mirrorless camera", ["Z50 Mirrorless Camera (16-50mm Kit)", "Alpha C Mirrorless Camera Kit", "Vlog V10 Mirrorless Camera"],
     ["Optix", "Lumen"], (52990, 89990), ["camera", "mirrorless", "photography", "vlog", "lens"]),
]


@dataclass(frozen=True)
class Item:
    sku: str
    shop: str
    slug: str
    title: str
    brand: str
    category: str
    product_type: str
    base_price: int
    mrp: int
    rating: float
    rating_count: int
    tags: tuple[str, ...]
    description: str
    phase: int = field(default=0)


def _slug(text: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in text)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def _round_price(x: float) -> int:
    return int(max(99, round(x / 10) * 10 - 1))


@lru_cache
def catalog() -> tuple[Item, ...]:
    rng = random.Random(2026)
    items: list[Item] = []
    for shop, category, ptype, models, brands, (lo, hi), tags in FAMILIES:
        for model in models:
            for brand in brands[: 2 if hi > 20000 or len(models) > 3 else len(brands)]:
                frac = (len(items) * 0.37) % 1
                base = _round_price(lo + (hi - lo) * (0.15 + 0.7 * rng.random() * (0.6 + 0.4 * frac)))
                mrp = _round_price(base * rng.uniform(1.15, 1.6))
                title = f"{brand} {model}"
                sku = hashlib.sha1(f"{shop}:{title}".encode()).hexdigest()[:10].upper()
                desc = (f"{title} — {ptype.lower()} from {brand}. "
                        f"{rng.choice(['Loved for its build quality.', 'Great value for everyday use.', 'A popular pick this season.', 'Backed by a 1-year warranty.'])}")
                items.append(Item(sku, shop, _slug(title), title, brand, category, ptype, base, mrp,
                                  round(rng.uniform(3.6, 4.8), 1), rng.randint(40, 4200), tuple(tags), desc, rng.randint(0, 40)))
    return tuple(items)


def by_shop(shop: str) -> list[Item]:
    return [i for i in catalog() if i.shop == shop]


def find(shop: str, slug: str) -> Item | None:
    return next((i for i in catalog() if i.shop == shop and i.slug == slug), None)


def find_sku(sku: str) -> Item | None:
    return next((i for i in catalog() if i.sku == sku), None)


def on_sale(item: Item, day: date) -> bool:
    return (day.toordinal() + item.phase) % 23 < 4


def price_on(item: Item, day: date) -> int:
    t = day.toordinal() + item.phase
    wobble = 1 + 0.025 * math.sin(2 * math.pi * t / 17)
    sale = 0.82 if on_sale(item, day) else 1.0
    return min(item.mrp, _round_price(item.base_price * wobble * sale))


def in_stock(item: Item, day: date) -> bool:
    return (day.toordinal() + item.phase * 7) % 37 != 0
