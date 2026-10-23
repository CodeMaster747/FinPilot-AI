"""Which email senders FinPilot may read: banks, card issuers, payment apps, merchants, billers, insurers and
investment platforms used in India. Everything else is never opened (and, for mailbox sync, never downloaded).

An entry matches the sender's domain or any subdomain of it ("alerts.hdfcbank.net" matches "hdfcbank.net");
entries containing "@" match one exact address (for big senders like Google, where only payment mail is wanted).
Every domain under RBI's dedicated ".bank.in" zone is a bank and is always allowed.
"""

from __future__ import annotations

BANK_ZONE = "bank.in"

EMAIL_ALLOWLIST: tuple[str, ...] = (
    # banks
    "hdfcbank.net", "hdfcbank.com", "icicibank.com", "sbi.co.in", "onlinesbi.sbi", "sbi.com", "axisbank.com", "kotak.com",
    "kotakbank.com", "yesbank.in", "idfcfirstbank.com", "idfcbank.com", "indusind.com", "federalbank.co.in", "aubank.in",
    "rblbank.com", "bandhanbank.com", "canarabank.com", "canarabank.in", "unionbankofindia.co.in", "bankofbaroda.com",
    "bankofbaroda.co.in", "bankofbaroda.in", "pnb.co.in", "pnbindia.in", "indianbank.in", "indianbank.co.in", "iob.in",
    "centralbankofindia.co.in", "bankofindia.co.in", "ucobank.com", "ucobank.co.in", "psbindia.com", "idbibank.com",
    "idbibank.co.in", "kvb.co.in", "karurvysyabank.co.in", "cityunionbank.com", "cityunionbank.in", "tmb.in",
    "southindianbank.com", "sib.co.in", "jkbank.com", "dcbbank.com", "equitasbank.com", "ujjivansfb.in", "esafbank.com",
    "hsbc.co.in", "sc.com", "dbs.com", "americanexpress.com", "americanexpress.co.in", "aexp.com",
    # cards, payments banks, wallets and UPI apps
    "sbicard.com", "bobfinancial.com", "getonecard.app", "fplt.in", "cred.club", "jupiter.money", "fi.money", "sliceit.com",
    "paytm.com", "paytmbank.com", "phonepe.com", "mobikwik.com", "amazonpay.in", "freecharge.in", "airtel.in", "airtel.com",
    "jiopaymentsbank.com", "finobank.com", "npci.org.in",
    "payments-noreply@google.com", "googlepay-noreply@google.com", "googleplay-noreply@google.com",
    # shopping
    "amazon.in", "flipkart.com", "myntra.com", "ajio.com", "nykaa.com", "meesho.com", "snapdeal.com", "tatacliq.com",
    "croma.com", "reliancedigital.in", "jiomart.com", "decathlon.in", "firstcry.com", "lenskart.com", "ikea.in",
    "pepperfry.com", "apple.com", "samsung.com", "boat-lifestyle.com",
    # food and groceries
    "swiggy.in", "zomato.com", "zepto.co", "zeptonow.com", "blinkit.com", "bigbasket.com", "dunzo.in", "eatsure.com",
    "dominos.co.in", "mcdonaldsindia.com",
    # travel and transport
    "uber.com", "olacabs.com", "rapido.bike", "irctc.co.in", "makemytrip.com", "goibibo.com", "cleartrip.com", "yatra.com",
    "redbus.in", "ixigo.com", "goindigo.in", "airindia.com", "airindia.in", "spicejet.com", "akasaair.com", "airbnb.com",
    "oyorooms.com", "booking.com", "agoda.com", "fastag.ihmcl.com", "nammayatri.in",
    # subscriptions and entertainment
    "netflix.com", "spotify.com", "jiohotstar.com", "hotstar.com", "primevideo.com", "youtube.com", "sonyliv.com", "zee5.com",
    "audible.in", "bookmyshow.com", "district.in", "pvrcinemas.com", "microsoft.com", "openai.com", "linkedin.com",
    "cult.fit", "curefit.com",
    # telecom, internet and utilities
    "jio.com", "vodafoneidea.com", "myvi.in", "bsnl.co.in", "actcorp.in", "tataplay.com", "dishtv.in", "tatapower.com",
    "adanielectricity.com", "bescom.co.in", "tnpdcl.org", "tangedco.org", "mahadiscom.in", "cesc.co.in", "torrentpower.com",
    "iocl.com", "bharatpetroleum.in", "hindustanpetroleum.com", "mahanagargas.com", "iglonline.net",
    # insurance
    "licindia.in", "policybazaar.com", "starhealth.in", "hdfcergo.com", "icicilombard.com", "iciciprulife.com",
    "hdfclife.com", "maxlifeinsurance.com", "axismaxlife.com", "sbilife.co.in", "bajajallianz.co.in", "tataaig.com",
    "careinsurance.com", "nivabupa.com", "acko.com", "godigit.com",
    # investments and loans
    "camsonline.com", "kfintech.com", "mfcentral.com", "zerodha.com", "zerodha.net", "groww.in", "upstox.com",
    "angelone.in", "kuvera.in", "paytmmoney.com", "nsdl.co.in", "cdslindia.com", "bajajfinserv.in", "tatacapital.com",
    "hdfccredila.com", "homecredit.co.in", "kreditbee.in", "moneyview.in", "navi.com",
    # health and services
    "practo.com", "apollo247.com", "apollopharmacy.in", "pharmeasy.in", "tata1mg.com", "netmeds.com", "urbancompany.com",
    # education
    "coursera.org", "udemy.com", "byjus.com", "unacademy.com",
)


def _domain_matches(domain: str, entry: str) -> bool:
    return domain == entry or domain.endswith("." + entry)


def sender_allowed(address: str, extra: tuple[str, ...] = ()) -> bool:
    """`address` is the bare email address (no display name)."""
    address = (address or "").strip().strip("<>").lower()
    domain = address.rsplit("@", 1)[-1]
    if not domain or "@" not in address:
        return False
    if _domain_matches(domain, BANK_ZONE):
        return True
    for entry in (*EMAIL_ALLOWLIST, *extra):
        entry = entry.lower()
        if "@" in entry:
            if address == entry:
                return True
        elif _domain_matches(domain, entry):
            return True
    return False


def gmail_from_terms(extra: tuple[str, ...] = ()) -> list[str]:
    """Search terms for Gmail's `from:` operator (domains match their subdomains too)."""
    return [BANK_ZONE, *EMAIL_ALLOWLIST, *extra]
