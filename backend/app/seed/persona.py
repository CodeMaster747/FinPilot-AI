"""Ground-truth generator for the demo persona.

Produces 24 months of transactions (ending on a given day) for Aarav Sharma, a software engineer in
Chennai, plus non-transaction events (bills, statements, subscription notices, usage signals,
failed payments). Renderers in sms.py / emails.py turn this truth into the raw SMS and emails the
capture pipeline ingests; the truth doubles as labelled data for evaluation.

Everything a module needs to find is planted deliberately: a subscription price hike, a dormant gym
membership, overlapping music services, a trial that converts to paid, a duplicate charge, an
out-of-pattern purchase, a new-merchant spike, own-account transfers, card bill payments, refunds,
a reversal, festival spikes and summer electricity bills.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

CARD_LIMIT = Decimal("200000.00")


@dataclass(frozen=True)
class AccountSpec:
    key: str
    name: str
    institution: str
    kind: str
    mask: str
    opening_balance: Decimal
    liquid: bool


ACCOUNTS = [
    AccountSpec("hdfc", "HDFC Savings", "HDFC Bank", "savings", "4521", Decimal("85000.00"), True),
    AccountSpec("icici", "ICICI Amazon Pay Credit Card", "ICICI Bank", "credit_card", "7788", Decimal("0.00"), False),
    AccountSpec("sbi", "SBI Savings", "State Bank of India", "savings", "9034", Decimal("42000.00"), True),
]


@dataclass
class TruthTxn:
    id: str
    ts: datetime
    account: str  # hdfc | icici | sbi
    direction: str  # debit | credit
    amount: Decimal
    merchant: str
    category: str
    channel: str  # upi | card | dcard | nach | imps | neft | atm | interest
    payee: str  # how the counterparty appears in bank alerts
    vpa: str | None = None
    ref: str = ""
    kind: str = "spend"  # spend | income | transfer_out | transfer_in | card_payment | card_payment_in | refund | reversal
    items: list[tuple[str, int, Decimal]] | None = None
    order_id: str | None = None
    restaurant: str | None = None
    merchant_email: str | None = None
    bank_email: bool = False
    otp: bool = False
    pair: str | None = None
    receipt: bool = False
    tags: tuple[str, ...] = ()
    balance_after: Decimal | None = None


@dataclass
class Notice:
    ts: datetime
    kind: str
    data: dict = field(default_factory=dict)


@dataclass
class Persona:
    start: date
    end: date
    accounts: list[AccountSpec]
    txns: list[TruthTxn]
    notices: list[Notice]

    def by_id(self) -> dict[str, TruthTxn]:
        return {t.id: t for t in self.txns}


def money(x: float, step: str = "1") -> Decimal:
    return Decimal(str(x)).quantize(Decimal(step), ROUND_HALF_UP).quantize(Decimal("0.01"))


RESTAURANTS = {
    "A2B - Adyar Ananda Bhavan": [("Masala Dosa", 115), ("Mini Tiffin", 185), ("Filter Coffee", 45), ("Ghee Pongal", 120), ("Rava Kesari", 70)],
    "Dindigul Thalappakatti": [("Chicken Biryani", 299), ("Mutton Biryani", 399), ("Chicken 65", 229), ("Onion Raitha", 40)],
    "Behrouz Biryani": [("Lazeez Chicken Biryani", 349), ("Murgh Makhani Biryani", 379), ("Gulab Jamun (2 pcs)", 99)],
    "Domino's Pizza": [("Farmhouse Pizza (Medium)", 459), ("Peppy Paneer Pizza (Medium)", 459), ("Garlic Breadsticks", 129), ("Choco Lava Cake", 109)],
    "Burger King": [("Whopper", 219), ("Crispy Veg Burger", 89), ("King Fries (Medium)", 119), ("Coke (Medium)", 79)],
    "Saravana Bhavan": [("South Indian Meals", 220), ("Parotta with Kurma", 140), ("Curd Rice", 110)],
    "The Bowl Company": [("Paneer Tikka Rice Bowl", 269), ("Chicken Teriyaki Bowl", 299), ("Cold Coffee", 129)],
    "Kailash Parbat": [("Pav Bhaji", 179), ("Chole Bhature", 199), ("Masala Chaas", 69)],
}
CAFES = [("Third Wave Coffee", "thirdwavecoffee@ybl"), ("Starbucks", "tatastarbucks@hdfcbank"), ("Chai Kings", "chaikings@okaxis")]
DINE_OUT = ["Absolute Barbecues", "Murugan Idli Shop", "Sangeetha Veg Restaurant", "Saravana Bhavan", "A2B"]
GROCERY_ITEMS = [
    ("Aashirvaad Atta 5kg", 289), ("Amul Taaza Milk 1L", 68), ("Tomato 1kg", 42), ("Onion 2kg", 78),
    ("Toor Dal 1kg", 165), ("Fortune Sunflower Oil 1L", 155), ("India Gate Basmati Rice 5kg", 549),
    ("Farm Eggs (12 pcs)", 96), ("Banana Robusta 1 dozen", 60), ("Brown Bread 400g", 50), ("Amul Curd 400g", 40),
    ("Tata Salt 1kg", 28), ("Surf Excel Matic 1kg", 235), ("Colgate MaxFresh 150g", 105), ("Green Tea 100 bags", 299),
    ("Paneer 200g", 90), ("Apples Shimla 1kg", 180), ("Potato 2kg", 70), ("Coriander Leaves", 15), ("Butter 100g", 58),
]
AMAZON_ITEMS = [
    ("USB-C Fast Charging Cable 1m", 349), ("Notebook A5 Ruled (Pack of 3)", 299), ("Running Socks (3 pairs)", 449),
    ("Yoga Mat 6mm Anti-Slip", 899), ("LED Desk Lamp with USB Port", 1299), ("Stainless Steel Water Bottle 1L", 599),
    ("Paperback: Atomic Habits", 399), ("Silicone Phone Case", 299), ("Wireless Mouse", 699), ("Resistance Bands Set", 549),
    ("Kitchen Weighing Scale", 649), ("Steel Lunch Box", 799), ("Laptop Stand Aluminium", 1499), ("Electric Kettle 1.5L", 1199),
]
WHEY = ("ProFuel Whey Protein 1kg (Chocolate)", 2399)
COFFEE = ("HillBean Arabica Coffee Beans 250g", 649)
DECATHLON_ITEMS = [
    ("Stride Run 100 Running Shoes", 2999), ("Dry-Fit Running T-Shirt", 499), ("Ankle Running Socks x3", 299),
    ("Yoga Mat 8mm", 999), ("Hex Dumbbell 5kg", 1299), ("Badminton Shuttlecocks x6", 449), ("Running Shorts", 599),
    ("Sports Water Bottle 650ml", 249), ("Fitness Resistance Band", 399), ("Cycling Gloves", 349),
]
FLIPKART_ITEMS = [("Bluetooth Speaker 10W", 1499), ("Bedsheet Double Cotton", 899), ("Pressure Cooker 3L", 1399), ("Power Bank 10000mAh", 999)]
MYNTRA_ITEMS = [("Men Slim Fit Casual Shirt", 1299), ("Men Running Joggers", 999), ("Cotton Kurta Set", 1899), ("Sneakers White", 2499)]
FOOD_TIMES = [(time(12, 40), time(14, 10)), (time(19, 45), time(22, 30))]


class PersonaBuilder:
    def __init__(self, end: date, seed: int = 7, days: int = 730, cutoff: datetime | None = None):
        self.end = end
        self.cutoff = cutoff or datetime.combine(end, time(23, 59, 59))
        self.start = end - timedelta(days=days - 1)
        self.rng = random.Random(seed * 100_003 + end.toordinal())
        self.txns: list[TruthTxn] = []
        self.notices: list[Notice] = []
        self._n = 0
        self._next = {"lpg": self.start + timedelta(days=9), "fuel": self.start + timedelta(days=3),
                      "decathlon": self.start + timedelta(days=17), "whey": self.start + timedelta(days=12),
                      "coffee": self.start + timedelta(days=5), "salon": self.start + timedelta(days=21),
                      "irctc": self.start + timedelta(days=50), "doctor": self.start + timedelta(days=40)}
        self.netflix_change = self._nth_day_after(end - timedelta(days=240), 14)
        self.audible_trial = end - timedelta(days=105)
        self.gym_last_class = end - timedelta(days=150)

    # -- helpers ---------------------------------------------------------------------------------
    @staticmethod
    def _nth_day_after(d: date, day: int) -> date:
        cand = d.replace(day=day) if d.day <= day else (d.replace(day=1) + timedelta(days=32)).replace(day=day)
        return cand

    def ref(self, digits: int = 12) -> str:
        return "".join(self.rng.choice("0123456789") for _ in range(digits))

    def order_id(self, prefix: str = "", digits: int = 10) -> str:
        return prefix + self.ref(digits)

    def at(self, d: date, lo: time, hi: time) -> datetime:
        a = datetime.combine(d, lo)
        b = datetime.combine(d, hi)
        return a + timedelta(seconds=self.rng.randint(0, max(1, int((b - a).total_seconds()))))

    def add(self, **kw) -> TruthTxn:
        self._n += 1
        kw.setdefault("ref", self.ref())
        t = TruthTxn(id=f"T{self._n:05d}", **kw)
        self.txns.append(t)
        return t

    def notice(self, ts: datetime, kind: str, **data) -> None:
        self.notices.append(Notice(ts, kind, data))

    def basket(self, catalog: list[tuple[str, int]], lo: int, hi: int) -> list[tuple[str, int, Decimal]]:
        items = []
        for name, price in self.rng.sample(catalog, self.rng.randint(lo, hi)):
            qty = 1 if price > 200 else self.rng.choice([1, 1, 2, 3])
            items.append((name, qty, Decimal(price)))
        return items

    @staticmethod
    def total(items: list[tuple[str, int, Decimal]]) -> Decimal:
        return sum((q * p for _, q, p in items), Decimal("0")).quantize(Decimal("0.01"))

    def salary(self, d: date) -> Decimal:
        fy_start = d.year if d.month >= 4 else d.year - 1
        return {2024: Decimal("112000"), 2025: Decimal("122000")}.get(fy_start, Decimal("133000"))

    @staticmethod
    def last_working_day(d: date) -> date:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = nxt - timedelta(days=1)
        while last.weekday() >= 5:
            last -= timedelta(days=1)
        return last

    # -- generation ------------------------------------------------------------------------------
    def build(self) -> Persona:
        d = self.start
        while d <= self.end:
            self._fixed(d)
            self._daily(d)
            d += timedelta(days=1)
        self._anomalies()
        self._refunds_and_reversal()
        self._review_cases()
        self._card_cycle()
        # nothing may happen after 'now' (the demo is generated up to the moment it is created)
        self.txns = sorted((t for t in self.txns if t.ts <= self.cutoff), key=lambda t: t.ts)
        self.notices = sorted((n for n in self.notices if n.ts <= self.cutoff), key=lambda n: n.ts)
        self._balances()
        return Persona(self.start, self.end, ACCOUNTS, self.txns, self.notices)

    def _fixed(self, d: date) -> None:
        r = self.rng
        if d.day == 1:
            self.add(ts=self.at(d, time(6, 0), time(7, 0)), account="hdfc", direction="debit", amount=Decimal("1799.00"),
                     merchant="Cult.fit", category="Sports & Fitness", channel="upi", payee="CULT FIT", vpa="cultfit@hdfcbank")
            self.notice(self.at(d, time(9, 0), time(11, 0)), "bill_due", biller="ACT Fibernet", amount=Decimal("1179.00"),
                        due=d.replace(day=6), account_no="ACT1042277")
        if d.day == 2:
            pair = f"P{d.isoformat()}"
            ts = self.at(d, time(9, 0), time(10, 30))
            self.add(ts=ts, account="hdfc", direction="debit", amount=Decimal("16500.00"), merchant="Self transfer",
                     category="Transfers", channel="imps", payee="SBI A/c XX9034", kind="transfer_out", pair=pair)
            self.add(ts=ts + timedelta(seconds=40), account="sbi", direction="credit", amount=Decimal("16500.00"),
                     merchant="Self transfer", category="Transfers", channel="imps", payee="AARAV SHARMA HDFC",
                     kind="transfer_in", pair=pair)
        if d.day == 3:
            self.add(ts=self.at(d, time(3, 0), time(5, 0)), account="icici", direction="debit", amount=Decimal("149.00"),
                     merchant="YouTube Premium", category="Subscriptions", channel="card", payee="GOOGLE*YOUTUBEPREMIUM")
        if d.day == 5:
            rent = Decimal("26500.00") if d >= date(2026, 2, 1) else Decimal("25000.00")
            self.add(ts=self.at(d, time(8, 0), time(10, 0)), account="hdfc", direction="debit", amount=rent,
                     merchant="Ramesh Kumar", category="Rent", channel="upi", payee="RAMESH KUMAR", vpa="rameshkumar@okicici")
        if d.day == 6:
            self.add(ts=self.at(d, time(10, 0), time(12, 0)), account="hdfc", direction="debit", amount=Decimal("1179.00"),
                     merchant="ACT Fibernet", category="Phone & Internet", channel="upi", payee="ACT FIBERNET", vpa="actfibernet@hdfcbank")
        if d.day == 7:
            for name, payee in (("ELSS Tax Saver SIP", "BSE LTD-ELSS TAXSAVER SIP"), ("Nifty 50 Index SIP", "BSE LTD-NIFTY50 INDEX SIP")):
                t = self.add(ts=self.at(d, time(6, 0), time(8, 0)), account="sbi", direction="debit", amount=Decimal("5000.00"),
                             merchant=name, category="Investments", channel="nach", payee=payee)
                self.notice(t.ts + timedelta(hours=r.randint(6, 30)), "sip_confirmation", scheme=name, amount=t.amount,
                            folio="7012345/88", units=round(5000 / r.uniform(48, 61), 3))
        if d.day == 10:
            self.add(ts=self.at(d, time(5, 0), time(7, 0)), account="hdfc", direction="debit", amount=Decimal("9850.00"),
                     merchant="Tata Capital", category="Loan EMI", channel="nach", payee="TATA CAPITAL LTD")
        if d.day == 14:
            price = Decimal("649.00") if d >= self.netflix_change else Decimal("499.00")
            self.add(ts=self.at(d, time(2, 0), time(4, 0)), account="icici", direction="debit", amount=price,
                     merchant="Netflix", category="Subscriptions", channel="card", payee="NETFLIX.COM")
        if d == self.netflix_change - timedelta(days=30):
            self.notice(self.at(d, time(11, 0), time(13, 0)), "price_change", service="Netflix", old=Decimal("499.00"),
                        new=Decimal("649.00"), effective=self.netflix_change)
        if d.day == 15:
            self.add(ts=self.at(d, time(6, 0), time(8, 0)), account="sbi", direction="debit", amount=Decimal("6200.00"),
                     merchant="SBI Education Loan", category="Loan EMI", channel="nach", payee="SBI EDU LOAN A/C 3345")
        if d.day == 10:
            self.notice(self.at(d, time(9, 0), time(11, 0)), "bill_due", biller="Airtel", amount=Decimal("699.00"),
                        due=d.replace(day=18), account_no="98840 12345")
        if d.day == 18:
            self.add(ts=self.at(d, time(7, 0), time(9, 0)), account="icici", direction="debit", amount=Decimal("699.00"),
                     merchant="Airtel", category="Phone & Internet", channel="card", payee="AIRTEL POSTPAID AUTOPAY")
        if d.day == 22:
            self.add(ts=self.at(d, time(4, 0), time(6, 0)), account="hdfc", direction="debit", amount=Decimal("119.00"),
                     merchant="Spotify", category="Subscriptions", channel="upi", payee="SPOTIFY INDIA", vpa="spotify@icici")
        if d.day == 25 and d.month in (1, 4, 7, 10):
            self.add(ts=self.at(d, time(9, 0), time(12, 0)), account="hdfc", direction="debit", amount=Decimal("499.00"),
                     merchant="JioHotstar", category="Subscriptions", channel="upi", payee="JIOHOTSTAR", vpa="jiohotstar@axisbank")
        if d == self.last_working_day(d):
            self.add(ts=self.at(d, time(10, 0), time(13, 0)), account="hdfc", direction="credit", amount=self.salary(d),
                     merchant="Zentrix Technologies", category="Salary", channel="neft", payee="ZENTRIX TECHNOLOGIES PVT LTD-SALARY",
                     kind="income")
        if (d.month, d.day) == (3, 15):
            self.add(ts=self.at(d, time(8, 0), time(9, 0)), account="icici", direction="debit", amount=Decimal("1499.00"),
                     merchant="Amazon Prime", category="Subscriptions", channel="card", payee="AMAZON PRIME MEMBERSHIP")
        if (d.month, d.day) == (2, 20):
            t = self.add(ts=self.at(d, time(11, 0), time(13, 0)), account="hdfc", direction="debit", amount=Decimal("24000.00"),
                         merchant="LIC of India", category="Insurance", channel="upi", payee="LIC OF INDIA", vpa="licofindia@hdfcbank")
            self.notice(t.ts + timedelta(hours=3), "lic_receipt", amount=t.amount, policy="884512367")
        if (d.month, d.day) == (1, 12):
            t = self.add(ts=self.at(d, time(11, 0), time(13, 0)), account="icici", direction="debit", amount=Decimal("18500.00"),
                         merchant="Star Health Insurance", category="Insurance", channel="card", payee="STAR HEALTH AND ALLIED INS",
                         bank_email=True)
            self.notice(t.ts + timedelta(hours=2), "insurance_receipt", amount=t.amount, policy="P/131112/01/2026/004512")
        # bimonthly electricity (Tamil Nadu bills every two months); summer bills are the big ones
        if d.month % 2 == 0 and d.day == 1:
            amount = {6: r.randint(4800, 5300), 8: r.randint(3600, 4200), 4: r.randint(2100, 2500)}.get(d.month, r.randint(1450, 1900))
            self.notice(self.at(d, time(10, 0), time(12, 0)), "bill_due", biller="TNPDCL", amount=Decimal(amount),
                        due=d.replace(day=15), account_no="09-123-456-789")
            self._pending_power = (d.replace(day=12), Decimal(amount))
        if getattr(self, "_pending_power", None) and self._pending_power[0] == d:
            self.add(ts=self.at(d, time(18, 0), time(21, 0)), account="hdfc", direction="debit", amount=self._pending_power[1],
                     merchant="TNPDCL", category="Utilities", channel="upi", payee="TNPDCL", vpa="tnpdcl@sbi")
            self._pending_power = None
        # interest credits at quarter end
        if d.month in (3, 6, 9, 12) and (d + timedelta(days=1)).day == 1:
            self.add(ts=self.at(d, time(20, 0), time(23, 0)), account="hdfc", direction="credit", amount=money(r.uniform(600, 1150)),
                     merchant="Interest Credit", category="Interest", channel="interest", payee="INTEREST", kind="income")
            self.add(ts=self.at(d, time(20, 0), time(23, 0)), account="sbi", direction="credit", amount=money(r.uniform(280, 520)),
                     merchant="Interest Credit", category="Interest", channel="interest", payee="INTEREST", kind="income")
        # Audible: trial -> paid
        if d == self.audible_trial:
            self.notice(self.at(d, time(20, 0), time(22, 0)), "trial_started", service="Audible",
                        trial_end=d + timedelta(days=30), price=Decimal("199.00"))
        if d == self.audible_trial + timedelta(days=23):
            self.notice(self.at(d, time(9, 0), time(10, 0)), "trial_ending", service="Audible",
                        trial_end=self.audible_trial + timedelta(days=30), price=Decimal("199.00"))
        if d >= self.audible_trial + timedelta(days=30) and (d - (self.audible_trial + timedelta(days=30))).days % 30 == 0:
            self.add(ts=self.at(d, time(1, 0), time(3, 0)), account="icici", direction="debit", amount=Decimal("199.00"),
                     merchant="Audible", category="Subscriptions", channel="card", payee="AUDIBLE.IN")

    def _daily(self, d: date) -> None:
        r = self.rng
        weekend = d.weekday() >= 4  # Fri-Sun
        # food delivery (Swiggy / Zomato) with order emails
        if r.random() < (0.36 if weekend else 0.17):
            self._food_order(d)
        if r.random() < (0.30 if d.weekday() >= 5 else 0.0):
            name = r.choice(DINE_OUT)
            self.add(ts=self.at(d, time(19, 30), time(22, 0)), account="icici", direction="debit",
                     amount=money(r.uniform(650, 2600)), merchant=name, category="Dining Out", channel="card",
                     payee=name.upper(), bank_email=r.random() < 0.7)
        if r.random() < 0.13:
            name, vpa = r.choice(CAFES)
            self.add(ts=self.at(d, time(8, 30), time(18, 30)), account="hdfc", direction="debit", amount=money(r.uniform(180, 460)),
                     merchant=name, category="Dining Out", channel="upi", payee=name.upper(), vpa=vpa)
        # groceries
        if d.weekday() == 5 or (d.weekday() == 6 and r.random() < 0.15):
            items = self.basket(GROCERY_ITEMS, 6, 12)
            card = r.random() < 0.65
            self.add(ts=self.at(d, time(9, 0), time(12, 0)), account="icici" if card else "hdfc", direction="debit",
                     amount=self.total(items), merchant="BigBasket", category="Groceries", channel="card" if card else "upi",
                     payee="BIGBASKET" if card else "SUPERMARKET GROCERY SUPPLIES", vpa=None if card else "bigbasket@hdfcbank",
                     items=items, order_id=self.order_id("BB"), merchant_email="bigbasket", bank_email=card and r.random() < 0.7)
        if d.weekday() < 5 and r.random() < 0.18:
            name, vpa = r.choice([("Zepto", "zepto@ybl"), ("Blinkit", "blinkit@axisbank")])
            items = self.basket(GROCERY_ITEMS, 1, 4)
            self.add(ts=self.at(d, time(17, 0), time(21, 30)), account="hdfc", direction="debit", amount=self.total(items),
                     merchant=name, category="Groceries", channel="upi", payee=name.upper(), vpa=vpa, items=items)
        if r.random() < 0.07:
            items = self.basket(GROCERY_ITEMS, 3, 8)
            self.add(ts=self.at(d, time(10, 0), time(20, 0)), account="hdfc", direction="debit", amount=self.total(items),
                     merchant="Nilgiris", category="Groceries", channel="dcard", payee="NILGIRIS SUPERMARKET", items=items,
                     receipt=True)
        # transport
        if r.random() < (0.22 if weekend else 0.33):
            uber = r.random() < 0.6
            self.add(ts=self.at(d, time(8, 0), time(22, 0)), account="hdfc", direction="debit", amount=money(r.uniform(110, 460)),
                     merchant="Uber" if uber else "Ola", category="Transport", channel="upi",
                     payee="UBER INDIA SYSTEMS" if uber else "ANI TECHNOLOGIES PVT LTD",
                     vpa="uber.rides@hdfcbank" if uber else "olacabs@icici", merchant_email="uber" if uber else None)
        if d.weekday() == 0 and d.day <= 7:
            self.add(ts=self.at(d, time(8, 0), time(9, 30)), account="hdfc", direction="debit", amount=Decimal("500.00"),
                     merchant="Chennai Metro", category="Transport", channel="upi", payee="CMRL TRAVEL CARD", vpa="cmrl@sbi")
        if d >= self._next["fuel"]:
            name, payee = r.choice([("HP Petrol Pump", "HPCL OMR FUEL STATION"), ("Indian Oil", "IOCL VELACHERY COCO"),
                                    ("Bharat Petroleum", "BPCL GUINDY")])
            self.add(ts=self.at(d, time(8, 0), time(20, 0)), account="icici", direction="debit", amount=money(r.uniform(1400, 2600)),
                     merchant=name, category="Fuel", channel="card", payee=payee, bank_email=r.random() < 0.7)
            self._next["fuel"] = d + timedelta(days=r.randint(11, 14))
        if d >= self._next["lpg"]:
            self.add(ts=self.at(d, time(10, 0), time(16, 0)), account="hdfc", direction="debit", amount=Decimal("905.00"),
                     merchant="Indane Gas", category="Utilities", channel="upi", payee="INDANE GAS", vpa="indane@sbi")
            self._next["lpg"] = d + timedelta(days=r.randint(40, 50))
        # shopping
        if r.random() < 0.07:
            self._amazon(d, self.basket(AMAZON_ITEMS, 1, 2))
        if d >= self._next["whey"]:
            self._amazon(d, [(WHEY[0], 1, Decimal(WHEY[1]))], replenish=True)
            self._next["whey"] = d + timedelta(days=r.randint(42, 48))
        if d >= self._next["coffee"]:
            self._amazon(d, [(COFFEE[0], 1, Decimal(COFFEE[1]))], replenish=True)
            self._next["coffee"] = d + timedelta(days=r.randint(28, 34))
        if r.random() < 0.025:
            items = self.basket(FLIPKART_ITEMS, 1, 1)
            self.add(ts=self.at(d, time(11, 0), time(23, 0)), account="hdfc", direction="debit", amount=self.total(items),
                     merchant="Flipkart", category="Shopping", channel="upi", payee="FLIPKART INTERNET", vpa="flipkart@axisbank",
                     items=items, order_id=self.order_id("OD", 15), merchant_email="flipkart")
        if r.random() < 0.016:
            items = self.basket(MYNTRA_ITEMS, 1, 2)
            self.add(ts=self.at(d, time(12, 0), time(23, 0)), account="icici", direction="debit", amount=self.total(items),
                     merchant="Myntra", category="Fashion", channel="card", payee="MYNTRA DESIGNS", items=items,
                     order_id=self.order_id("", 16), merchant_email="myntra", otp=True, bank_email=True)
        if d >= self._next["decathlon"]:
            items = self.basket(DECATHLON_ITEMS, 1, 3)
            self.add(ts=self.at(d, time(11, 0), time(19, 0)), account="hdfc", direction="debit", amount=self.total(items),
                     merchant="Decathlon", category="Sports & Fitness", channel="dcard", payee="DECATHLON SPORTS INDIA", items=items,
                     receipt=True)
            self._next["decathlon"] = d + timedelta(days=r.randint(38, 56))
        # health (sensitive category)
        if r.random() < 0.03:
            self.add(ts=self.at(d, time(9, 0), time(21, 0)), account="hdfc", direction="debit", amount=money(r.uniform(180, 950)),
                     merchant="Apollo Pharmacy", category="Healthcare", channel="upi", payee="APOLLO PHARMACY", vpa="apollopharmacy@hdfcbank")
        if d >= self._next["doctor"]:
            self.add(ts=self.at(d, time(10, 0), time(18, 0)), account="icici", direction="debit", amount=Decimal("800.00"),
                     merchant="Kauvery Hospital", category="Healthcare", channel="card", payee="KAUVERY HOSPITAL CHENNAI")
            self._next["doctor"] = d + timedelta(days=r.randint(80, 110))
        # entertainment & personal care & travel
        if r.random() < (0.07 if d.weekday() >= 5 else 0.01):
            self.add(ts=self.at(d, time(14, 0), time(21, 0)), account="icici", direction="debit", amount=money(r.uniform(420, 1250)),
                     merchant="PVR INOX", category="Entertainment", channel="card", payee="PVR INOX LTD", bank_email=r.random() < 0.7)
        if d >= self._next["salon"]:
            self.add(ts=self.at(d, time(11, 0), time(19, 0)), account="hdfc", direction="debit", amount=money(r.uniform(450, 1100)),
                     merchant="Naturals Salon", category="Personal Care", channel="upi", payee="NATURALS SALON VELACHERY",
                     vpa="naturalssalon@ybl")
            self._next["salon"] = d + timedelta(days=r.randint(35, 48))
        if d >= self._next["irctc"]:
            self.add(ts=self.at(d, time(9, 0), time(22, 0)), account="hdfc", direction="debit", amount=money(r.uniform(850, 2400)),
                     merchant="IRCTC", category="Travel", channel="upi", payee="IRCTC E-TICKETING", vpa="irctc@sbi")
            self._next["irctc"] = d + timedelta(days=r.randint(75, 110))
        if r.random() < 0.035:
            self.add(ts=self.at(d, time(7, 0), time(22, 0)), account="hdfc", direction="debit",
                     amount=Decimal(r.choice([2000, 3000, 5000])), merchant="ATM Withdrawal", category="Cash Withdrawal",
                     channel="atm", payee="ATM VELACHERY MAIN RD")
        # festival spikes in the ten days before Diwali
        for diwali in (date(2024, 10, 31), date(2025, 10, 20), date(2026, 11, 8)):
            if diwali - timedelta(days=10) <= d < diwali and r.random() < 0.45:
                choice = r.random()
                if choice < 0.45:
                    self._amazon(d, self.basket(AMAZON_ITEMS + [("Smart LED Bulb (Pack of 2)", 899), ("Diwali Gift Hamper", 1499)], 2, 4))
                elif choice < 0.75:
                    items = self.basket(MYNTRA_ITEMS, 2, 3)
                    self.add(ts=self.at(d, time(12, 0), time(23, 0)), account="icici", direction="debit", amount=self.total(items),
                             merchant="Myntra", category="Fashion", channel="card", payee="MYNTRA DESIGNS", items=items,
                             order_id=self.order_id("", 16), merchant_email="myntra", otp=True, bank_email=True)
                else:
                    self.add(ts=self.at(d, time(10, 0), time(20, 0)), account="hdfc", direction="debit",
                             amount=money(r.uniform(1200, 2600)), merchant="Sri Krishna Sweets", category="Dining Out",
                             channel="upi", payee="SRI KRISHNA SWEETS", vpa="srikrishnasweets@okaxis")
        # noise that must never become transactions
        if r.random() < 0.025:
            self.notice(self.at(d, time(9, 0), time(22, 0)), "failed_upi", amount=money(r.uniform(150, 2500)),
                        payee=r.choice(["SWIGGY", "ZEPTO", "UBER INDIA SYSTEMS", "IRCTC E-TICKETING"]))
        if r.random() < 0.40:
            self.notice(self.at(d, time(8, 0), time(21, 0)), "promo_sms", variant=r.randint(0, 99))
        if r.random() < 0.06:
            self.notice(self.at(d, time(8, 0), time(21, 0)), "promo_email", variant=r.randint(0, 99))
        if r.random() < 0.05:
            self.notice(self.at(d, time(8, 0), time(23, 0)), "personal_sms", variant=r.randint(0, 99))
        if r.random() < 0.05:
            self.notice(self.at(d, time(7, 0), time(23, 0)), "newsletter_email", variant=r.randint(0, 99))
        if d.weekday() == 0:
            self.notice(datetime.combine(d, time(9, 15)), "balance_alert", account="hdfc")
        if d.day == 1:
            self.notice(datetime.combine(d, time(9, 5)), "balance_alert", account="sbi")
        # gym usage signal: class bookings stop five months before the end (dormant membership)
        if d <= self.gym_last_class and d.weekday() in (1, 3, 5) and r.random() < 0.7:
            self.notice(self.at(d - timedelta(days=1), time(19, 0), time(22, 0)), "class_booking",
                        workout=r.choice(["HRX Workout", "Yoga", "Boxing", "Strength & Conditioning", "Dance Fitness"]),
                        center="Cult Velachery", when=datetime.combine(d, time(r.choice([6, 7, 18, 19]), 0)))

    def _food_order(self, d: date, at: datetime | None = None, amount: Decimal | None = None) -> TruthTxn:
        r = self.rng
        swiggy = r.random() < 0.55
        restaurant = r.choice(list(RESTAURANTS))
        items = self.basket(RESTAURANTS[restaurant], 1, 3)
        subtotal = self.total(items)
        if amount is not None:
            while subtotal >= amount and len(items) > 1:
                items = items[:-1]
                subtotal = self.total(items)
            fees = amount - subtotal  # make the email's line items add up to the charged amount
        else:
            fees = money(r.choice([25, 30, 35, 39]) + float(subtotal) * 0.05)  # delivery + taxes
        total = subtotal + fees
        lo, hi = r.choice(FOOD_TIMES)
        card = r.random() < 0.4
        return self.add(ts=at or self.at(d, lo, hi), account="icici" if card else "hdfc", direction="debit", amount=total,
                        merchant="Swiggy" if swiggy else "Zomato", category="Food Delivery", channel="card" if card else "upi",
                        payee=("SWIGGY" if swiggy else "ZOMATO") if card else ("BUNDL TECHNOLOGIES" if swiggy else "ZOMATO LTD"),
                        vpa=None if card else ("swiggy@icici" if swiggy else "zomato@hdfcbank"), items=items + [("Delivery fee & taxes", 1, fees)],
                        order_id=self.order_id("", 12 if swiggy else 10), restaurant=restaurant,
                        merchant_email="swiggy" if swiggy else "zomato", bank_email=card and r.random() < 0.7)

    def _amazon(self, d: date, items: list[tuple[str, int, Decimal]], replenish: bool = False) -> TruthTxn:
        r = self.rng
        return self.add(ts=self.at(d, time(10, 0), time(23, 30)), account="icici", direction="debit", amount=self.total(items),
                        merchant="Amazon", category="Shopping", channel="card", payee="AMAZON PAY INDIA", items=items,
                        order_id=f"40{r.randint(1, 9)}-{self.ref(7)}-{self.ref(7)}", merchant_email="amazon",
                        otp=r.random() < 0.6, bank_email=r.random() < 0.7, tags=("replenish",) if replenish else ())

    def _anomalies(self) -> None:
        end = self.end
        # 1) duplicate charge: the same Zomato order debited twice, six minutes apart (distinct refs)
        first = self._food_order(end - timedelta(days=45), at=datetime.combine(end - timedelta(days=45), time(20, 14)),
                                 amount=Decimal("642.00"))
        first.account, first.channel, first.vpa, first.merchant = "hdfc", "upi", "zomato@hdfcbank", "Zomato"
        first.payee, first.merchant_email, first.bank_email = "ZOMATO LTD", "zomato", False
        self.add(ts=first.ts + timedelta(minutes=6), account="hdfc", direction="debit", amount=Decimal("642.00"),
                 merchant="Zomato", category="Food Delivery", channel="upi", payee="ZOMATO LTD", vpa="zomato@hdfcbank",
                 tags=("anomaly:duplicate",))
        # 2) out-of-pattern purchase at a merchant never seen before
        self.add(ts=datetime.combine(end - timedelta(days=20), time(17, 42)), account="icici", direction="debit",
                 amount=Decimal("38999.00"), merchant="Croma", category="Electronics", channel="card", payee="CROMA - INFINITI RETAIL",
                 otp=True, bank_email=True, tags=("anomaly:large",))
        # 3) new-merchant spike (unknown merchant -> ML fallback has to categorise it)
        self.add(ts=datetime.combine(end - timedelta(days=35), time(13, 5)), account="hdfc", direction="debit",
                 amount=Decimal("12499.00"), merchant="QuickFix Appliances", category="Electronics", channel="upi",
                 payee="QUICKFIX APPLIANCES", vpa="quickfixappl@ybl", tags=("anomaly:new_merchant",))

    def _refunds_and_reversal(self) -> None:
        r = self.rng
        amazon = [t for t in self.txns if t.merchant == "Amazon" and t.ts.date() < self.end - timedelta(days=20)]
        for t in r.sample(amazon, min(3, len(amazon))):
            refund = self.add(ts=t.ts + timedelta(days=r.randint(5, 12), hours=r.randint(1, 5)), account="icici", direction="credit",
                              amount=t.amount, merchant="Amazon", category="Shopping", channel="card", payee="AMAZON PAY INDIA",
                              kind="refund", order_id=t.order_id, merchant_email="amazon_refund")
            refund.items = t.items
        # a UPI debit that the bank reverses two days later (same reference)
        d = self.end - timedelta(days=150)
        orig = self.add(ts=datetime.combine(d, time(21, 5)), account="hdfc", direction="debit", amount=Decimal("1250.00"),
                        merchant="IRCTC", category="Travel", channel="upi", payee="IRCTC E-TICKETING", vpa="irctc@sbi",
                        tags=("reversed",))
        self.add(ts=orig.ts + timedelta(days=2, hours=3), account="hdfc", direction="credit", amount=orig.amount,
                 merchant="IRCTC", category="Travel", channel="upi", payee="IRCTC E-TICKETING", kind="reversal", ref=orig.ref,
                 pair=orig.id)

    def _review_cases(self) -> None:
        """Real-world cases a careful app should ask about, so the review queue has work in the demo. Fixed values
        and no RNG draws, so every other part of the persona is unchanged."""
        end = self.end
        # a barber known only by name: nothing for the merchant list or the model to go on (twice: "apply to all")
        for i, days in enumerate((38, 9)):
            d = end - timedelta(days=days)
            self.add(ts=datetime.combine(d, time(18, 20 + i)), account="hdfc", direction="debit", amount=Decimal("350.00"),
                     merchant="M Selvam", category="Personal Care", channel="upi", payee="M SELVAM", vpa="selvam.m1987@okaxis",
                     ref=f"6281{d:%y%m%d}{11 + i}", tags=("review:unknown_payee",))
        # an unfamiliar gift shop
        d = end - timedelta(days=4)
        self.add(ts=datetime.combine(d, time(19, 5)), account="hdfc", direction="debit", amount=Decimal("1850.00"),
                 merchant="The Brown Bear Co", category="Shopping", channel="upi", payee="THE BROWN BEAR CO", vpa="brownbearco@ybl",
                 ref=f"6282{d:%y%m%d}31", tags=("review:unknown_payee",))
        # a merchant's refund notice without an amount (the credit comes days later), so the app asks
        myntra = [t for t in self.txns if t.merchant == "Myntra" and t.ts.date() <= end - timedelta(days=6)]
        if myntra:
            t = max(myntra, key=lambda x: x.ts)
            self.notice(datetime.combine(end - timedelta(days=2), time(11, 30)), "refund_initiated", merchant="Myntra",
                        order_id=t.order_id, item=t.items[0][0] if t.items else "your item")

    def _card_cycle(self) -> None:
        """ICICI card: statement on the 18th, paid in full from HDFC on the 3rd."""
        card = sorted((t for t in self.txns if t.account == "icici"), key=lambda t: t.ts)
        d = self.start
        statements = []
        while d <= self.end:
            if d.day == 18:
                statements.append(d)
            d += timedelta(days=1)
        prev = datetime.combine(self.start - timedelta(days=1), time(23, 59))
        for sd in statements:
            cut = datetime.combine(sd, time(0, 0))
            spend = sum((t.amount if t.direction == "debit" else -t.amount for t in card if prev < t.ts <= cut), Decimal("0"))
            prev = cut
            if spend <= 0:
                continue
            due = sd + timedelta(days=18)
            minimum = (spend * Decimal("0.05")).quantize(Decimal("1")) + Decimal("0.00")
            self.notice(datetime.combine(sd, time(10, 30)), "card_statement", total=spend, minimum=minimum, due=due,
                        period_start=(sd - timedelta(days=30)), period_end=sd - timedelta(days=1))
            pay_day = sd + timedelta(days=15)
            if pay_day > self.end:
                continue
            pair = f"CC{sd.isoformat()}"
            ts = self.at(pay_day, time(9, 0), time(12, 0))
            self.add(ts=ts, account="hdfc", direction="debit", amount=spend, merchant="ICICI Credit Card Payment",
                     category="Credit Card Payment", channel="imps", payee="ICICI BANK CREDIT CARD XX7788", kind="card_payment", pair=pair)
            self.add(ts=ts + timedelta(minutes=self.rng.randint(5, 50)), account="icici", direction="credit", amount=spend,
                     merchant="ICICI Credit Card Payment", category="Credit Card Payment", channel="imps",
                     payee="PAYMENT RECEIVED", kind="card_payment_in", pair=pair)

    def _balances(self) -> None:
        bal = {a.key: a.opening_balance for a in ACCOUNTS}
        for t in self.txns:
            if t.account == "icici":
                # available limit = limit - outstanding
                bal["icici"] += t.amount if t.direction == "debit" else -t.amount
                t.balance_after = (CARD_LIMIT - bal["icici"]).quantize(Decimal("0.01"))
            else:
                bal[t.account] += t.amount if t.direction == "credit" else -t.amount
                t.balance_after = bal[t.account].quantize(Decimal("0.01"))
        self.final_balances = dict(bal)


def build_persona(end: date, seed: int = 7, cutoff: datetime | None = None) -> Persona:
    return PersonaBuilder(end, seed, cutoff=cutoff).build()
