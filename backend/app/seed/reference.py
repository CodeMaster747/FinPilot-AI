"""Reference data: categories and the curated merchant alias map (Indian + global merchants).

Aliases are matched as whole words on normalised text (see services.categorization.normalize),
so 'swiggy@icici', 'SWIGGY*ORDER 8812' and 'Swiggy Instamart' all resolve correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CategorySpec:
    name: str
    group: str
    kind: str  # income | expense | savings | transfer
    essential: bool = False
    discretionary: bool = False
    sensitive: bool = False
    icon: str = "circle"


CATEGORIES: list[CategorySpec] = [
    CategorySpec("Salary", "Income", "income", icon="briefcase"),
    CategorySpec("Interest", "Income", "income", icon="percent"),
    CategorySpec("Other Income", "Income", "income", icon="coins"),
    CategorySpec("Rent", "Housing", "expense", essential=True, icon="house"),
    CategorySpec("Groceries", "Food", "expense", essential=True, icon="shopping-basket"),
    CategorySpec("Utilities", "Bills", "expense", essential=True, icon="zap"),
    CategorySpec("Phone & Internet", "Bills", "expense", essential=True, icon="wifi"),
    CategorySpec("Loan EMI", "Loans", "expense", essential=True, icon="landmark"),
    CategorySpec("Insurance", "Financial", "expense", essential=True, icon="shield"),
    CategorySpec("Healthcare", "Health", "expense", essential=True, sensitive=True, icon="heart-pulse"),
    CategorySpec("Transport", "Transport", "expense", essential=True, icon="car"),
    CategorySpec("Fuel", "Transport", "expense", essential=True, icon="fuel"),
    CategorySpec("Education", "Education", "expense", essential=True, icon="graduation-cap"),
    CategorySpec("Cash Withdrawal", "Cash", "expense", essential=True, icon="banknote"),
    CategorySpec("Fees & Charges", "Financial", "expense", essential=True, icon="receipt"),
    CategorySpec("Dining Out", "Food", "expense", discretionary=True, icon="utensils"),
    CategorySpec("Food Delivery", "Food", "expense", discretionary=True, icon="bike"),
    CategorySpec("Shopping", "Shopping", "expense", discretionary=True, icon="shopping-bag"),
    CategorySpec("Electronics", "Shopping", "expense", discretionary=True, icon="laptop"),
    CategorySpec("Fashion", "Shopping", "expense", discretionary=True, icon="shirt"),
    CategorySpec("Sports & Fitness", "Lifestyle", "expense", discretionary=True, icon="dumbbell"),
    CategorySpec("Entertainment", "Lifestyle", "expense", discretionary=True, icon="clapperboard"),
    CategorySpec("Subscriptions", "Lifestyle", "expense", discretionary=True, icon="repeat"),
    CategorySpec("Personal Care", "Lifestyle", "expense", discretionary=True, icon="sparkles"),
    CategorySpec("Travel", "Lifestyle", "expense", discretionary=True, icon="plane"),
    CategorySpec("Investments", "Savings", "savings", icon="trending-up"),
    CategorySpec("Transfers", "Transfers", "transfer", icon="arrow-left-right"),
    CategorySpec("Credit Card Payment", "Transfers", "transfer", icon="credit-card"),
    CategorySpec("Misc", "Other", "expense", discretionary=True, icon="circle-help"),
]


@dataclass(frozen=True)
class MerchantSpec:
    name: str
    category: str
    aliases: tuple[str, ...]
    tags: tuple[str, ...] = field(default_factory=tuple)  # interest signals for Smart Picks


M = MerchantSpec
MERCHANTS: list[MerchantSpec] = [
    # Food delivery
    M("Swiggy", "Food Delivery", ("swiggy", "swgy", "bundl technologies")),
    M("Zomato", "Food Delivery", ("zomato", "zomt", "zomato ltd")),
    M("EatSure", "Food Delivery", ("eatsure", "rebel foods")),
    # Groceries
    M("BigBasket", "Groceries", ("bigbasket", "bbnow", "big basket", "supermarket grocery supplies"), ("groceries",)),
    M("Zepto", "Groceries", ("zepto", "kiranakart", "zeptonow"), ("groceries",)),
    M("Blinkit", "Groceries", ("blinkit", "grofers", "blink commerce"), ("groceries",)),
    M("Swiggy Instamart", "Groceries", ("instamart", "swiggy instamart"), ("groceries",)),
    M("Nilgiris", "Groceries", ("nilgiris", "nilgiris supermarket"), ("groceries",)),
    M("DMart", "Groceries", ("dmart", "avenue supermarts"), ("groceries",)),
    M("Reliance Smart", "Groceries", ("reliance smart", "smart bazaar", "reliance fresh", "reliance retail")),
    M("Amma Stores", "Groceries", ("amma stores",)),
    # Dining out
    M("Third Wave Coffee", "Dining Out", ("third wave coffee", "thirdwave", "twc"), ("coffee",)),
    M("Starbucks", "Dining Out", ("starbucks", "tata starbucks"), ("coffee",)),
    M("Murugan Idli Shop", "Dining Out", ("murugan idli", "murugan idli shop")),
    M("Sangeetha Veg Restaurant", "Dining Out", ("sangeetha", "sangeetha veg")),
    M("Absolute Barbecues", "Dining Out", ("absolute barbecues", "absolute barbecue", "abs barbecue")),
    M("Chai Kings", "Dining Out", ("chai kings",), ("tea",)),
    M("McDonald's", "Dining Out", ("mcdonalds", "mc donalds", "hardcastle restaurants")),
    M("Domino's", "Dining Out", ("dominos", "domino s", "jubilant foodworks")),
    M("KFC", "Dining Out", ("kfc", "devyani")),
    M("Saravana Bhavan", "Dining Out", ("saravana bhavan", "hotel saravana")),
    M("A2B", "Dining Out", ("a2b", "adyar ananda bhavan")),
    # Transport
    M("Uber", "Transport", ("uber", "uber india", "uber rides")),
    M("Ola", "Transport", ("olacabs", "ola cabs", "ani technologies", "ola money")),
    M("Rapido", "Transport", ("rapido", "roppen")),
    M("Chennai Metro", "Transport", ("cmrl", "chennai metro", "chennai metro rail")),
    M("Namma Yatri", "Transport", ("namma yatri", "juspay namma yatri")),
    # Fuel
    M("HP Petrol Pump", "Fuel", ("hpcl", "hp petrol", "hindustan petroleum", "hp pay")),
    M("Indian Oil", "Fuel", ("iocl", "indian oil", "indianoil")),
    M("Bharat Petroleum", "Fuel", ("bpcl", "bharat petroleum")),
    # Bills
    M("TNPDCL", "Utilities", ("tnpdcl", "tangedco", "tneb", "tamil nadu power")),
    M("Indane Gas", "Utilities", ("indane", "indian oil lpg", "indanegas")),
    M("Chennai Metro Water", "Utilities", ("cmwssb", "metro water")),
    M("Airtel", "Phone & Internet", ("airtel", "bharti airtel", "airtel postpaid", "airtel payments")),
    M("Jio", "Phone & Internet", ("jio", "reliance jio", "jio prepaid")),
    M("ACT Fibernet", "Phone & Internet", ("act fibernet", "atria convergence", "actcorp", "act broadband")),
    # Loans & insurance
    M("Tata Capital", "Loan EMI", ("tata capital", "tatacapital", "tata capital ltd")),
    M("SBI Education Loan", "Loan EMI", ("sbi edu loan", "sbi education loan")),
    M("LIC of India", "Insurance", ("lic of india", "licindia", "life insurance corporation", "lic premium")),
    M("Star Health Insurance", "Insurance", ("star health", "starhealth", "star health insurance")),
    M("ICICI Lombard", "Insurance", ("icici lombard",)),
    # Health (sensitive: never used to infer interests)
    M("Apollo Pharmacy", "Healthcare", ("apollo pharmacy", "apollo pharmacies", "apollopharmacy")),
    M("MedPlus", "Healthcare", ("medplus", "optival health")),
    M("Kauvery Hospital", "Healthcare", ("kauvery", "kauvery hospital")),
    M("Practo", "Healthcare", ("practo",)),
    # Shopping
    M("Amazon", "Shopping", ("amazon", "amzn", "amazon in", "amazon pay", "amazon seller services")),
    M("Flipkart", "Shopping", ("flipkart", "fkrt", "flipkart internet")),
    M("Meesho", "Shopping", ("meesho", "fashnear")),
    M("Croma", "Electronics", ("croma", "infiniti retail"), ("electronics",)),
    M("Reliance Digital", "Electronics", ("reliance digital",), ("electronics",)),
    M("Myntra", "Fashion", ("myntra", "myntra designs"), ("fashion",)),
    M("Ajio", "Fashion", ("ajio",), ("fashion",)),
    M("Zara", "Fashion", ("zara", "inditex"), ("fashion",)),
    M("Nykaa", "Personal Care", ("nykaa", "fsn e commerce"), ("personal care",)),
    M("Naturals Salon", "Personal Care", ("naturals salon", "naturals"), ("personal care",)),
    # Sports & fitness
    M("Decathlon", "Sports & Fitness", ("decathlon", "decathlon sports"), ("running", "fitness", "sports")),
    M("Cult.fit", "Sports & Fitness", ("cult fit", "cultfit", "curefit", "cure fit"), ("fitness", "gym")),
    # Entertainment & subscriptions
    M("PVR INOX", "Entertainment", ("pvr", "pvr inox", "inox"), ("movies",)),
    M("BookMyShow", "Entertainment", ("bookmyshow", "bigtree entertainment"), ("movies", "events")),
    M("Netflix", "Subscriptions", ("netflix", "netflix com")),
    M("Spotify", "Subscriptions", ("spotify", "spotify india"), ("music",)),
    M("YouTube Premium", "Subscriptions", ("youtube", "youtube premium", "google youtube", "youtubepremium"), ("music",)),
    M("Amazon Prime", "Subscriptions", ("amazon prime", "prime video", "primevideo")),
    M("JioHotstar", "Subscriptions", ("jiohotstar", "hotstar", "disney hotstar", "star india")),
    M("Audible", "Subscriptions", ("audible", "audible in"), ("books",)),
    M("Google Play", "Subscriptions", ("google play", "googleplay", "google services")),
    M("ChatGPT", "Subscriptions", ("openai", "chatgpt", "openai llc")),
    M("Apple Services", "Subscriptions", ("apple com bill", "apple services", "itunes", "apple media services")),
    M("Microsoft 365", "Subscriptions", ("microsoft", "msft", "microsoft 365", "xbox")),
    M("SonyLIV", "Subscriptions", ("sonyliv", "sony liv", "culver max")),
    M("ZEE5", "Subscriptions", ("zee5", "zee entertainment")),
    M("JioSaavn", "Subscriptions", ("jiosaavn", "saavn"), ("music",)),
    M("Amazon Music", "Subscriptions", ("amazon music",), ("music",)),
    M("Tata Play", "Subscriptions", ("tata play", "tatasky", "tata sky")),
    M("LinkedIn Premium", "Subscriptions", ("linkedin",)),
    M("Swiggy One", "Subscriptions", ("swiggy one",)),
    M("Zomato Gold", "Subscriptions", ("zomato gold",)),
    # Travel & education
    M("IRCTC", "Travel", ("irctc", "indian railway"), ("travel",)),
    M("MakeMyTrip", "Travel", ("makemytrip", "mmt"), ("travel",)),
    M("IndiGo", "Travel", ("indigo", "interglobe aviation"), ("travel",)),
    M("Coursera", "Education", ("coursera",), ("learning",)),
    M("Udemy", "Education", ("udemy",), ("learning",)),
    # Investments
    M("ELSS Tax Saver SIP", "Investments", ("elss", "taxsaver sip", "elss taxsaver")),
    M("Nifty 50 Index SIP", "Investments", ("nifty50 index", "index sip", "nifty 50 index")),
    M("BSE StAR MF", "Investments", ("bse ltd", "bse limited", "bse star mf")),
    M("Zerodha", "Investments", ("zerodha",)),
    M("Groww", "Investments", ("groww", "nextbillion")),
    # Cash, fees, income, transfers
    M("ATM Withdrawal", "Cash Withdrawal", ("atm", "cash withdrawal", "nfs atm", "atm wdl")),
    M("Bank Charges", "Fees & Charges", ("sms charges", "annual fee", "chrg", "service charge", "late fee")),
    M("Interest Credit", "Interest", ("int pd", "interest credit", "interest paid", "int credit", "interest of")),
    M("ICICI Credit Card Payment", "Credit Card Payment", ("icici bank credit card", "icici credit card", "icici cc payment")),
]

# Generic vocabulary used to train the ML fallback for merchants the alias map has never seen.
CATEGORY_VOCAB: dict[str, list[str]] = {
    "Groceries": ["supermarket", "mart", "provision", "kirana", "general stores", "vegetables", "fresh", "daily needs", "departmental store", "organic store"],
    "Dining Out": ["restaurant", "cafe", "coffee", "bistro", "dhaba", "bakery", "sweets", "kitchen", "biryani house", "mess", "tiffin center", "juice shop", "bar and grill"],
    "Food Delivery": ["food delivery", "order delivery", "cloud kitchen"],
    "Transport": ["cabs", "taxi", "travels", "auto", "parking", "toll", "metro rail", "bus pass"],
    "Fuel": ["petroleum", "fuel station", "petrol pump", "service station", "filling station", "fuels"],
    "Utilities": ["electricity", "power", "water board", "gas agency", "lpg"],
    "Phone & Internet": ["broadband", "fibernet", "telecom", "mobile recharge", "postpaid", "internet services"],
    "Healthcare": ["pharmacy", "medicals", "hospital", "clinic", "diagnostics", "dental", "chemist", "labs"],
    "Shopping": ["online shopping", "retail", "enterprises", "store", "emporium", "bazaar", "traders", "gift shop"],
    "Electronics": ["electronics", "mobiles", "digital", "computers", "appliances", "gadgets", "laptop world"],
    "Fashion": ["fashion", "garments", "textiles", "boutique", "silks", "footwear", "clothing"],
    "Sports & Fitness": ["sports", "fitness", "gym", "yoga studio", "athletics", "cycles"],
    "Entertainment": ["cinemas", "multiplex", "gaming", "amusement", "bowling", "theatre"],
    "Subscriptions": ["subscription", "premium membership", "streaming", "monthly plan"],
    "Personal Care": ["salon", "spa", "beauty", "parlour", "cosmetics", "grooming"],
    "Travel": ["airlines", "aviation", "railways", "holidays", "tours", "hotel booking", "resorts"],
    "Insurance": ["insurance", "assurance", "policy premium", "general insurance"],
    "Loan EMI": ["finance ltd", "loan emi", "capital emi", "housing finance", "credit emi"],
    "Education": ["academy", "school", "college", "tuition", "institute", "courses", "learning"],
    "Investments": ["mutual fund", "sip", "securities", "broking", "amc", "demat"],
}

# Senders whose email is relevant (everything else is dropped by the pre-filter, unread).
# The demo persona's own payees: installed only for the demo account, never for real users (a real user's salary
# credit must not be named after the persona's employer).
PERSONA_MERCHANTS: list[MerchantSpec] = [
    M("Zentrix Technologies", "Salary", ("zentrix", "zentrix technologies", "salary", "sal credit")),
    M("SBI Education Loan", "Loan EMI", ("education loan", "edu loan")),
]
