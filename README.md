# FinPilot AI

A personal-finance assistant for India that builds your financial picture from the **bank SMS and emails you already
get**, but only after you allow each source, one at a time and for stated purposes. Uploading receipts, bills and
statements stays optional. A built-in crawler watches (demo) online stores and recommends only products you can
afford without touching your bills, goals or safety buffer.

Sem VII Full Stack Development project, SSN College of Engineering:
Jeya Sangavi R · Rahul Akshath Rajendran · Rakshitha S

---

## Run it

```bash
python3 run.py          # Windows: py run.py
```

That is the only step. You need **Python 3.11 or newer**; nothing else needs to be installed or configured.

- **First run:** `run.py` creates a private environment in `.venv` and installs the pinned packages. This needs
  internet once and takes a few minutes. It then sets up the database, trains the models (about 3 s) and generates
  the demo data (about 5 s).
- **The browser opens** at http://localhost:8000. Click **Try the demo**.
- **After the first run, everything works offline.** No Docker, database server, API keys, accounts, paid AI or
  bank login is involved. Busy ports are swapped for free ones automatically.
- **Node.js is not needed.** The web app ships pre-built in `frontend/out`.

| Command | What it does |
|---|---|
| `python3 run.py` | Start the app (and open the browser) |
| `python3 run.py --no-browser` | Start without opening a browser |
| `python3 run.py reset` | Wipe local data and regenerate the demo |
| `python3 run.py test` | Run the backend test suite |
| `python3 run.py build-frontend` | Rebuild the web app (needs Node.js; only for UI development) |

The demo persona, **Aarav Sharma** (a salaried software engineer in Chennai), has 24 months of messages ending
today. If you start the app on a later day, the demo is regenerated automatically, so it never looks stale.
Demo login, if asked: `demo@finpilot.ai` / `demo1234`.

---

## Demo script (about 10 minutes)

1. **Dashboard:** balance across accounts, *safe to spend this month*, the 90-day forecast band, unusual
   transactions and insights.
2. **Connections** (the consent centre):
   - Each source has its own permission, two purposes (record transactions; Smart Picks), a backfill window and an
     append-only consent history.
   - In the **phone simulator**, send *UPI payment to Swiggy*: it becomes a transaction. Then, in the **mail
     simulator**, deliver *Swiggy receipt for your last order*: the same transaction gains line items instead of
     being counted twice. Open it to see both messages as evidence.
   - Send *OTP for a card payment*: it is ignored and never stored. *Promotional loan offer (-P)* is dropped
     before it is even read.
3. **Scan a receipt:** try *Decathlon — a tilted phone photo*. Text recognition runs in the browser, the photo is
   straightened, and fields come with confidence scores and boxes. The receipt is matched to its card payment and
   attached to it.
4. **Review:** set *M Selvam* (a barber known only by name) to *Personal Care* with "remember". Both of his
   payments update, and future ones will too. There is also a Myntra refund email with no amount to resolve.
5. **Forecast:**
   - The backtest table compares Prophet with two baselines, with an honest reading of the result.
   - Try a what-if purchase of ₹45,000.
6. **Subscriptions:** a dormant gym, a free trial that became paid, a Netflix price rise (with the email as proof)
   and overlapping video/music services, ranked by ₹ saved per year.
7. **Tax:**
   - New vs old regime for FY 2025-26 and Tax Year 2026-27.
   - 80C (now s.123), HRA, deduction headroom and advance tax.
   - Export as PDF or CSV.
8. **Insights & coach:** ask *"Can I afford a ₹60,000 laptop?"* or tap a suggested question. The answer shows its
   intent and confidence.
9. **Smart Picks:**
   - The affordability breakdown, then the three tiers: *Buy now*, *For your goals*, *Save up for*.
   - Open a product for its 90-day price history and verdict.
   - **Crawl now:** watch *BlockedMart* get skipped because its robots.txt disallows crawling.
   - Turn off "Also use for Smart Picks" for SMS on Connections. Picks stop using that data and nothing is marked
     "buy now". Turn it back on afterwards.
10. **Connections:** revoke email, then **Delete data** (messages and the transactions that only they supported).
11. **Settings → System & model quality:** the measured numbers below, plus **Run OCR benchmark** in the browser.
    Finish with **Reset the demo**.

---

## What it does

**Capture, with consent per source.** SMS and email are separate data sources. Nothing is read before you grant a
source in a dialog that shows:
- what is read and what is never read;
- what is stored and for how long;
- what the app will never do;
- two unticked purposes: *record transactions* (required) and *Smart Picks* (optional).

You can pause, resume, revoke or delete a source's data at any time. Every change is recorded with the notice version
and its hash. The design follows the consent principles of India's DPDP Act 2023; it does not claim compliance.

**Feeding a source.** No phone or Gmail account is needed. Sources are fed from:
- a **sample inbox/mailbox** (the demo persona's messages);
- **file import**: an Android *SMS Backup & Restore* XML, CSV or pasted text for SMS; `.eml` or `.mbox` for email
  (see [`samples/`](samples/));
- the **live simulators**.

All three go through the same pipeline:

1. **Pre-filter.** Promotional DLT headers (`-P`), personal numbers and non-allowlisted email senders are dropped
   before anything is stored.
2. **Classify** into 12 message kinds (TF-IDF + logistic regression). A safety rule ensures OTPs are never stored.
3. **Extract** amount, direction, account, payee/UPI ID, reference, date and balance. Per-bank templates are tried
   first, then a generic extractor; every field carries a confidence and its position in the text. Email receipts
   use schema.org `Order` markup when present.
4. **Reconcile:**
   - reference-number matching;
   - one transaction per real payment across SMS and email;
   - own-account transfers and card bill payments paired, so they don't count as spending;
   - reversals, refunds and receipt enrichment.
5. **Categorise:** your rules, then a merchant list (~80 merchants with UPI aliases), then ML. Anything uncertain
   goes to **Review**, and your answers become rules.

Raw message text is encrypted (Fernet) and deleted after 90 days; extracted fields are kept.

**Optional uploads:**
- **Receipts:** OCR with tesseract.js, entirely in the browser, with boxes and per-field confidence.
- **Digital PDF bills:** read from the text layer.
- **Bank-statement CSV wizard:** column mapping; rows already captured from SMS or email are skipped.
- **Manual entry.**

**Analysis:**
- **Categories & anomalies:** robust z-score per merchant, IsolationForest, duplicate charges, and large spends at
  new merchants.
- **Forecast:**
  - Recurring schedule (salary, rent, EMIs, SIPs, subscriptions, bills) plus Prophet on the remaining day-to-day
    flow (weekly/yearly seasonality, Indian holidays).
  - 80% band from predictive samples, a what-if and a low-balance warning.
  - Rolling-origin backtest against baselines. It falls back to the baseline automatically if Prophet can't run.
- **Subscriptions:** interval and amount detection plus email evidence. Flags price rises, dormant subscriptions,
  trial → paid and overlaps.
- **Tax:**
  - Both regimes, with 87A rebate, marginal relief, surcharge and cess.
  - 80C/s.123, 80D, 80E, 24(b), HRA and 80TTA, detected from transactions.
  - Headroom tips and the advance-tax schedule; CSV/PDF export.
  - FY 2025-26 under the Income-tax Act 1961, and Tax Year 2026-27 under the Income-tax Act 2025.
- **Insights & coach:**
  - A ranked insight feed.
  - An intent-based coach (13 intents, including affordability, recommendations and privacy) that answers from the
    same metric functions as the pages.
  - An honest fallback when it isn't sure.
- **Budgets & goals:** monthly limits with pace markers; goals with monthly targets. They feed insights, the coach
  and affordability.

**Smart Picks:**
- **Crawler:** visits only the bundled demo storefronts (TechKart, FitStop, HomeNest, DailyCart, plus BlockedMart,
  which robots.txt disallows). It reads robots.txt (with Crawl-delay) and the sitemaps, then schema.org `Product`
  JSON-LD, and records price history. It runs every 6 hours, or via *Crawl now*.
- **Affordability:**
  - safety buffer = max(your floor, one month of must-pays);
  - safe-to-spend never dips into the buffer, upcoming dues or goal contributions, and also respects the
    pessimistic 60-day forecast;
  - this month's wants budget.
- **Tiers:**
  - *Buy now* must fit all of the above and keep the forecast above the buffer. It is limited to essentials until
    the emergency fund is in place. A property-based test (Hypothesis) checks the rule.
  - *For your goals* matches what you are already saving for.
  - *Save up for* comes with a monthly plan.
- **Relevance:** your wishlist, goals, regular purchases and interests, learned **only from sources you allowed for
  Smart Picks**.
- **Guardrails:** a weekly cap, no urgency wording, and no affiliate links or paid ranking.

---

## Measured results

Measured on 10 October 2026 on this machine (macOS, Apple Silicon, Python 3.14) and shown live in Settings → System &
model quality. Message and capture figures use synthetic data with known answers. The demo persona is regenerated for
the current date, so a few figures (counts, forecast errors) shift slightly from day to day.

| What | Result |
|---|---|
| Message type, macro F1 (held-out test split, 1,070 messages) | 100% |
| Unseen bank formats (Axis, Kotak), type / amount / direction | 100% / 100% / 100% |
| Hand-written challenge set (other banks and merchants), type / amount / direction | 96.6% / 100% / 100% |
| One record per real payment across SMS + email (dedup precision / recall, 1,583 payments) | 100% / 100% |
| Own-account transfers found / false transfers | 100% / 0 |
| Category accuracy on captured payments | 99.8% (the 3 misses are deliberately ambiguous payees, sent to Review) |
| Email receipts attached to the right payment (532) | 100% |
| Category model on freshly generated noisy merchant names (25 classes) | 91.7% accuracy, 91.5% macro F1 |
| Coach intent on held-out paraphrases (26) | 84.6% |
| Forecast error, mean absolute daily error over 6 rolling 30-day backtests | Seasonal naive ₹10,067 · naive + known schedule ₹1,518 · **Prophet + known schedule ₹1,466** |
| Smart Picks precision@10 (vs most-reviewed products) | **100%** vs 80% |
| Receipt OCR in the browser (merchant, date, total on 3 sample images incl. a tilted photo) | 9/9 fields, about 0.5 s per receipt |
| Backend tests (pytest + Hypothesis) | 59 passed, on Python 3.14 and 3.11 |
| End-to-end tests (Playwright, the demo script above) | 14 passed |

**Reading the forecast result honestly.** Knowing the user's schedule does most of the work: it cuts the error by
85% against the seasonal-naive baseline. Prophet, which models the day-to-day spending on top, adds about 3%. WAPE is
reported instead of MAPE because daily net cash flow often crosses zero.

---

## How it is built

```
python3 run.py
 └─ one Python process
     ├─ FastAPI on :8000 ── /api/v1/*  (JSON API, cookie sessions, CSRF header check)
     │                    └ /*        (the pre-built Next.js static site, same origin → no CORS)
     ├─ demo stores on :8090 (a second Uvicorn server: storefronts, robots.txt, sitemaps, JSON-LD)
     ├─ job runner (thread pool, progress in the jobs table) + scheduler (crawl 6 h, nightly analytics, retention purge)
     └─ SQLite in WAL mode (data/finpilot.db) via SQLAlchemy 2 + Alembic migrations
```

| Layer | Tools |
|---|---|
| Backend | FastAPI, Uvicorn, SQLAlchemy 2, Alembic, Pydantic 2, PyJWT, pwdlib (bcrypt), cryptography (Fernet) |
| ML & data | scikit-learn, Prophet, pandas, NumPy, rapidfuzz, dateparser |
| Documents & crawling | pdfplumber, ReportLab, httpx, protego (robots.txt), BeautifulSoup + lxml, defusedxml |
| Frontend | Next.js 16 (static export), React 19, TypeScript, Tailwind CSS 4, shadcn/ui on Base UI, TanStack Query, Recharts, tesseract.js |
| Tests | pytest, Hypothesis, Playwright |

**Decisions that keep it reliable.**
- **Money:** stored as integer paise and handled as `Decimal`, never floats.
- **Model training:** models train in seconds at first start, so there are no binary model files to ship.
- **Self-contained demo:** everything the demo needs (persona, messages, receipts, stores, catalogue) is generated
  deterministically by the app itself.
- **Receipt OCR runs in the browser,** so no system Tesseract or OpenCV is needed.
- **No paid or networked AI:** the coach is an intent classifier with templated answers computed from your data.

```
FinPilot AI/
├─ run.py                 one-command launcher
├─ backend/
│  ├─ app/
│  │  ├─ api/v1/          REST endpoints
│  │  ├─ services/        consent, ingestion pipeline, receipts, forecasting, subscriptions, tax, picks, scraper, coach, insights
│  │  ├─ ml/              training and evaluation
│  │  ├─ seed/            demo persona and its SMS/email/receipt renderers
│  │  ├─ demo_store/      the crawlable storefronts
│  │  ├─ models/ db/ core/ jobs/
│  ├─ alembic/            migrations
│  └─ tests/              59 tests
├─ frontend/              Next.js source; out/ is the pre-built site the backend serves
├─ e2e/                   Playwright suite (cd e2e && npm ci && npx playwright install chromium && npx playwright test)
└─ samples/               files to try the imports and receipt scanning with your own account
```

Runtime data (the database, uploads, trained models and the generated secret key) lives in `data/`, which is created on
first run and safe to delete.

---

## Troubleshooting

- **"Preparing demo data…" on first start:** wait about a minute. The login page shows progress.
- **Port 8000 is busy:** the app picks the next free port and prints the address.
- **Prophet can't run on a machine:** the forecast falls back to the baseline model and says so. Every other feature
  is unaffected.
- **Start over:** `python3 run.py reset`.

## Limits, stated plainly

- **Synthetic demo data:** the persona and its messages are synthetic. Real bank formats vary more; that is why there
  is a held-out format test, a hand-written challenge set and a review queue.
- **Demo stores only:** the crawler visits only the bundled demo stores, never the live internet.
- **Planning tool, not tax advice:** tax figures are estimates. The 2026-27 slabs follow the announced
  Income-tax Act 2025 rules.
- **Tested on macOS (Apple Silicon):** `run.py` is written to be cross-platform and every dependency ships wheels
  for Windows and Linux, but those platforms were not tested.
