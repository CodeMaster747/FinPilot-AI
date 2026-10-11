# Plan: Build FinPilot AI as a one-command app with no Docker — consented SMS/email capture and Smart Picks

## Context

The user wants the whole app built and ready to demo at the final review:

- Every feature works.
- It runs from the code alone: no Docker, no database server, no system packages, no accounts or keys.
- Anything unnecessary, unreliable or hard to set up is removed.

Two feature changes carry over:

1. **SMS and email analysis.** Each source is used only after explicit permission. Uploading receipts and bills stays optional.
2. **A scheduled scraper that recommends affordable products.** It weighs income, savings, expenses, habits, goals and the forecast, so recommendations never put the user's finances at risk.

Every module from the review deck stays, in simplified form. `FinPilot AI/` is empty, so the app is built from scratch there.

**Decided with the user**

- **No Docker.**
- **All deck modules, simplified.**
- **SMS/email feeds that need no accounts.** These are:

  - a sample inbox and mailbox;
  - file import;
  - a live simulator.

  Gmail, IMAP and phone apps are out.
- **Bundled demo stores.** The crawler only visits these, never the live internet.

**Original target machine:** arm64 Mac with Python 3.14 and Node 26 installed, and no Postgres or Tesseract. A later verification was also completed on Windows x64 with Python 3.11.9 and Node 22.22.0; details are recorded at the end of this plan.

## How it's run (this is the acceptance criterion)

```
python3 run.py          # Windows: py run.py
```

On the first run, this creates `.venv`, installs pinned dependencies (a few minutes, needs internet once), sets up the database, trains the models and generates the demo data. It then opens http://localhost:8000. **Try the demo** logs in as a persona with 24 months of data ending today.

- **After the first run, everything works offline.**
- **No configuration.** Secrets are generated into `data/` the first time it runs. Busy ports are swapped for free ones automatically.
- **Node is not needed to run the app.** The frontend ships prebuilt and the backend serves it; Node is only needed to rebuild the UI.
- **Extra commands:**
  - `python3 run.py reset` — wipe the data and regenerate it.
  - `python3 run.py test` — run the backend tests.
- **Every page works with real data.** Background jobs (forecast, crawl, picks) finish within about 2 minutes of first boot.
- **New users work too.** Register → onboarding → consent → load the sample inbox or import a file → the app fills with their data.

## Architecture

One Python process, started by `run.py`:

- **Main server, 127.0.0.1:8000.**
  - Serves `/api/v1/*` (FastAPI) and the **Next.js static export** (`frontend/out`) from the same origin, so there's no CORS.
  - Login cookies are httpOnly and same-origin, and requests that change data must carry an `X-Requested-With` header.
- **Demo store server, 127.0.0.1:8090.** A second uvicorn server running in the same event loop, serving the storefront websites the crawler visits.
- **Job runner and scheduler.**
  - Background work runs on a thread pool and is tracked in a `jobs` table that the UI polls.
  - A scheduler thread runs the recurring work:
    - a crawl every 6 hours;
    - every night, in order: forecast → subscriptions/anomalies → insights → affordability → picks;
    - a daily retention purge.
  - At startup it also runs anything overdue.
- **Database.** SQLite in WAL mode (`data/finpilot.db`) through SQLAlchemy 2. Alembic migrations run at startup (in batch mode, which SQLite needs).
- **Money.** Stored as integer paise (SQLite has no exact decimal type) and handled as `Decimal` in code. Never floats.
- **Stale demo data.** At startup, if the demo data ends before today, the demo user is regenerated automatically, so there's no manual step before presenting.

**Stack.** These are the deck's choices, simplified for no Docker. Versions are pinned and tested on Python 3.14; any Python 3.11 or newer is supported.

- **Backend:**
  - Web and data: FastAPI, Uvicorn, SQLAlchemy 2 (SQLite), Alembic, Pydantic v2.
  - Auth and encryption: PyJWT, pwdlib[bcrypt], cryptography (Fernet).
  - ML: Prophet 1.5, pandas, NumPy, scikit-learn.
  - Documents: pdfplumber, ReportLab.
  - Crawling and parsing: httpx, protego, beautifulsoup4 + lxml, defusedxml, dateparser, rapidfuzz.
  - Tests: pytest + Hypothesis.
- **Frontend:**
  - Next.js 16 (`output: 'export'`), React 19, TypeScript 5.9.
  - Tailwind v4, shadcn/ui, lucide-react, sonner.
  - TanStack Query 5, Recharts 3, react-hook-form + zod.
  - **tesseract.js 7** for OCR in the browser. Its worker, core and English model are bundled under `public/ocr`.
  - Fonts via @fontsource.

**Removed compared with the deck and the original plan:**

- Docker, Postgres, Redis, Celery.
- Server-side Tesseract and OpenCV. OCR runs in the browser instead, and the image never leaves the device.
- Gmail, IMAP and the real-phone webhook.
- Live-internet crawling, Scrapy and Ollama.
- The two-URL CORS split.
- The Next.js server at runtime.

## Layout (`FinPilot AI/`)

```
run.py  README.md  samples/ (sms_backup.xml, sms.csv, inbox.mbox, receipts/*.png, bill.pdf, statement.csv)
backend/ requirements.txt  alembic/  tests/
  app/ server.py (both servers + job runner + scheduler)  main.py  bootstrap.py
       core/ (config, security, crypto, money, deps, errors)  db/  models/  schemas/  repositories/  api/v1/
       services/ consent ingestion receipts categorization anomaly forecasting subscriptions tax
                 insights coach budgets scraper picks metrics(shared)  jobs/ (runner, scheduler)
       ml/ (train + evaluate)  seed/ (persona → SMS/email/receipt/CSV renderers, catalog)  demo_store/
frontend/ src/…  public/ocr/  out/ (prebuilt, served by FastAPI)
e2e/ (optional Playwright suite)      data/ (runtime: db, uploads, models, secret; gitignored)
```

## Data model

- **From the original plan:** users, accounts, transactions, categories, merchants, merchant_aliases, category_rules, receipts, import_batches, budgets, goals, subscriptions, anomalies, insights, forecasts, forecast_metrics, chat_messages, model_artifacts.
- **Auth and jobs:** refresh_tokens, jobs.
- **Capture:**
  - data_sources;
  - consent_events (append-only);
  - ingested_messages:
    - unique `(data_source_id, external_id)`;
    - `fields` stored as `{value, confidence, span}`;
    - `body_enc`, kind, status, transaction_id, match_role, match_score;
  - transaction_items (line items);
  - upcoming_payments;
  - balance_snapshots.
- **Picks:** product_sources, crawl_runs, products, product_price_history, wishlist_items, affordability_snapshots, product_recommendations.
- **New columns:**
  - `transactions.origin`, `transactions.is_transfer`;
  - `categories.is_essential`;
  - `users.preferences` (JSON), `users.is_demo`.
- **Rules that apply everywhere:**
  - every query on user data filters on `user_id`;
  - the product catalog is shared by all users.

## Features

### Consent & data sources

- **Two sources need consent: SMS and Email.** Nothing is read until the user grants that source in its dialog, which shows:

  - an itemised notice: what's read, which senders, what's stored, how long it's kept, and what's never done;
  - two separate unticked purposes:
    - *record transactions, bills and subscriptions* (required);
    - *use for Smart Picks* (optional);
  - a backfill window.
- **Feeds:**

  - **Sample inbox/mailbox:** the demo persona's messages.
  - **Import:**
    - SMS from a backup XML file, CSV or pasted text;
    - email from `.eml` or `.mbox` files.
  - **Live simulator:** a phone panel and a mail panel, offering quick templates (UPI debit, salary, OTP, promo, bill due, order receipt) or free text. Messages go through the same `ingest_message()` path as everything else.
- **Controls:**

  - pause/resume;
  - revoke;
  - **delete data**: removes the source's messages and any transaction that exists only because of it;
  - consent history.

  A paused or revoked source refuses all ingestion.
- **Uploads stay optional.** Receipts/bills, CSV statements and manual entry are always available.
- **Privacy:**

  - non-financial messages are dropped before anything is stored;
  - raw bodies are encrypted (Fernet) and deleted after the retention period (default 90 days), while the extracted fields stay;
  - Smart Picks only uses data from sources where its purpose was granted, plus uploads and manual entries;
  - the design follows the consent principles of India's DPDP Act 2023, but doesn't claim to be compliant.

### Capture pipeline (offline)

1. **Pre-filter:**
   - **SMS:** checks the DLT sender header.
     - A `-P` (promotional) header is dropped.
     - Personal numbers are dropped.
   - **Email:** sender domains must be on an allowlist.
   - **Both:** a keyword gate.
2. **Classify:** TF-IDF + logistic regression into transaction / otp / promo / bill_due / statement / subscription_notice / refund / failed_or_reversed / balance / other.
3. **Extract:**
   - Per-bank YAML regex templates are tried first, then a generic extractor.
   - **Fields:** ₹/Rs/INR amount (including lakh-style grouping), direction, account, UPI VPA or merchant, reference number, date, balance.
   - **Emails:** HTML is converted to text, schema.org `Order` JSON-LD is used when present, and line items are parsed.
4. **Reconcile:**
   - **Matching:** an exact reference-number match wins. Otherwise the score combines amount, account, time window and merchant similarity.
   - **Canonical record:** bank alerts own the transaction. Receipts and order emails **enrich** it rather than duplicate it.
   - **Special cases:**
     - transfers between the user's own accounts and card bill payments are paired as transfers;
     - reversals cancel the original;
     - refunds net against spending.
   - **Ambiguous matches:** grey-band scores go to review.
5. **Categorize:**
   1. user rules;
   2. the alias map (~200 merchants, including UPI VPA handles);
   3. the ML model;
   4. anything left becomes Misc and goes to review.
6. **Side outputs:**
   - upcoming payments;
   - balance snapshots;
   - subscription evidence.
7. **One review queue.** Corrections feed the alias map, the rules and the classifier.

### Optional uploads

- **`/scan` runs OCR in the browser** (tesseract.js). The backend's extraction heuristics then pick out the total, date, merchant, GSTIN/CGST/SGST and line items.
- **Review screen:** shows bounding boxes, with low-confidence fields highlighted.
- **Commit:** runs reconciliation, so a receipt enriches its card transaction.
- **Digital PDF bills:** read with pdfplumber.
- **CSV import:** a wizard with column mapping, also reconciled.
- **Manual entry.**

### Other modules (as in the plan doc, simplified)

- **Categorization & anomalies:**
  - rules → aliases → TF-IDF + logistic regression;
  - robust z-score, IsolationForest, duplicate charges, and new merchant + large amount;
  - all of it runs only on reconciled transactions that aren't transfers.
- **Forecasting:**
  - **Models:** Prophet (weekly and yearly seasonality, Indian holidays, a scheduled-outflow regressor) against a seasonal-naive + 3-month-mean baseline.
  - **Backtest:** rolling-origin, reporting MAE / RMSE / WAPE. MAPE is not used because it's undefined when net flow crosses zero.
  - **Balance projection:** bands come from `predictive_samples`, with a low-balance alert.
  - **What-if:** shows the effect of a purchase.
  - **Fallback:** if Prophet can't run on a machine, the module falls back to the baseline and says so.
- **Subscriptions:** interval and amount detection plus email evidence. Finds price hikes, dormant subscriptions, overlaps and trial→paid, ranked by ₹ saved per year.
- **Tax:**
  - **FY 2025-26:** Income-tax Act 1961.
  - **Tax Year 2026-27:** Income-tax Act 2025, projected. Its slabs, ₹75k standard deduction and ₹12L rebate are unchanged.
  - **Calculations:** old vs new regime with marginal relief and cess.
  - **Deductions and planning:** 80C (now s.123), 80D, 80E, 24(b) and HRA; headroom; advance-tax dates.
  - **Output:** CSV and PDF export, with a disclaimer.
- **Insights & coach / purchase advisor:**
  - a ranked insight feed;
  - an intent coach. Its intents are the doc's set plus `affordability_check`, `recommendation_query` and `privacy_query`. It shows suggested questions and has an honest fallback;
  - both use the same metric functions as the dashboard.
- **Budgets & goals:** create, edit and delete, with progress. They feed insights, the coach and affordability.

### Smart Picks (opt-in)

- **Demo storefronts (port 8090):**

  - **Shops:** TechKart, FitStop, HomeNest and DailyCart, plus **BlockedMart**, which robots.txt disallows.
  - **Products:** about 250, with fictional brands. Each product page carries schema.org Product/Offer/AggregateRating JSON-LD and a generated SVG image.
  - **Crawler signals:** sitemaps and a `Crawl-delay`.
  - **Prices:** a fixed daily schedule with rotating sales, so every crawl sees real changes.
- **Crawler:**

  - **Requests:** httpx with an identifying user agent; sitemaps are found through robots.txt.
  - **robots.txt:** protego checks every URL; disallowed URLs are logged and skipped.
  - **Parsing:** JSON-LD Product extraction, INR prices only.
  - **Storage:** upserts by canonical path and records price history when a price changes.
  - **Politeness:** waits between requests, retries with backoff, caps pages per run; `crawl_runs` keeps a log.
  - **Scheduling:** every 6 hours, plus a *Crawl now* button.
  - **First boot:** 90 days of history are backfilled from the price schedule.
- **Affordability** (computed nightly and on demand):

  - **Inputs:**
    - income = median monthly income credits over 6 months;
    - committed = rent/EMI/SIP + subscriptions + upcoming payments;
    - essential = 3-month median of the essential categories;
    - goals = Σ (target − saved) / months left.
  - **Derived values:**
    - surplus = income − committed − essential − goals;
    - buffer = max(floor, one month of committed + essential);
    - **safe_to_spend = max(0, min(liquid balance − buffer − dues and goal contributions before the next income, lowest lower-band 60-day forecast − buffer))**;
    - wants_left = discretionary budget (or 30% of income) − spending so far this month.
- **Tiers:**

  - **`buy_now`:** price ≤ min(safe_to_spend, wants_left), and the what-if keeps the lowest forecast balance at or above the buffer.
    - Only essentials and replenishment items qualify while the emergency fund is below 6× the buffer.
    - Goals are funded first, so a buy_now never delays one.
  - **`save_up`:** affordable within 12 months. Shown as "save ₹X/month for N months", with a one-click linked goal.
  - **`not_now`:** never shown as a recommendation.
- **Relevance:**

  - **Interest profile:** wishlist, goals, line items and discretionary categories and merchants. Health and pharmacy are excluded.
  - **Retrieval:** TF-IDF finds candidates.
  - **Scoring:** relevance + affordability headroom + value (discount against the 30-day median, Bayesian rating) + goal match, minus penalties for dismissed or owned items.
  - **Ranking:** at most 3 per category in the top 12, replenishment first.
  - **Explanations:** every pick stores its reasons and its what-if impact.
- **Guardrails:**

  - a weekly cap;
  - no urgency wording;
  - no affiliate links or paid ranking;
  - a pause toggle;
  - a disclaimer.

  Picks also appear on the dashboard, in insights ("price drop: now affordable") and in the coach, and there's "Check a price".

### Seed persona & bootstrap

- **Ground truth:** a fixed seed, covering 24 months that end today.

  - **Income and fixed costs:**
    - salary with an April raise;
    - rent, car EMI, ELSS SIPs, LIC, health insurance.
  - **Regular spending:**
    - groceries;
    - weekend-heavy dining;
    - transport;
    - electricity every two months, with a summer spike;
    - a Diwali spike.
  - **Seven subscriptions:** a price hike, a dormant gym, a Spotify + YouTube Premium overlap, and a trial.
  - **Injected anomalies.**
  - **Money movements:** self-transfers, card bill payments, refunds, failed/reversed payments, ATM withdrawals.
- **Renderers:**

  - SMS in 4 bank styles, including OTP and promo noise and balance alerts;
  - emails: alerts, receipts with line items, bills, statements, subscription notices;
  - receipt images, a PDF bill and a CSV statement;
  - ground-truth labels, kept for evaluation.

  `samples/` holds copies for trying the imports.
- **Bootstrap:**

  1. Train the base models (cached in `data/models`).
  2. Create categories/aliases, store sources and the demo user (consents recorded).
  3. Ingest the SMS and email through the real pipeline (about 20 s).
  4. Queue the rest: anomalies → subscriptions → forecast + backtest → tax → insights → crawl → price-history backfill → affordability → picks.

  The UI shows a "Preparing your data" banner while this runs.

## Frontend routes

| Route                     | Contents                                                                                                                    |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `/login`, `/register` | Auth, plus**Try the demo**                                                                                            |
| `/onboarding`           | Choose sources → consent dialogs → sample or import, or skip                                                              |
| `/dashboard`            | KPIs including safe-to-spend, cash-flow chart with forecast band, categories, anomalies, insights, new picks, source health |
| `/transactions`         | Filters, recategorise, bulk edit, CSV wizard, manual add, evidence drawer                                                   |
| `/connections`          | Consent centre: SMS and Email cards, purposes, backfill, imports, phone and mail simulators, pause/revoke/delete, history   |
| `/review`               | One queue, with the evidence alongside: a receipt with boxes, or a message with highlighted spans                           |
| `/scan`                 | Optional upload → OCR in the browser → review → commit                                                                   |
| `/forecast`             | 30/60/90 days, Prophet vs baseline table and chart, balance projection                                                      |
| `/subscriptions`        | Detected subscriptions, findings, savings                                                                                   |
| `/tax`                  | Year switch, regime comparison, deductions/headroom, advance tax, export                                                    |
| `/insights`             | Feed, plus coach chat with suggested questions                                                                              |
| `/budgets`              | Budgets and goals                                                                                                           |
| `/picks`                | Picks by tier with reasons, price sparkline and what-if; wishlist; check a price; stores, crawl log,*Crawl now*           |
| `/settings`             | Profile, categories, rules, preferences, data export, reset demo,**system & model quality**                           |

Dynamic data uses query parameters rather than dynamic route segments, which keeps the static export simple. Load the `dataviz` skill before writing the first chart.

## Build phases

Each phase ends with `python3 run.py` working and its gate passing.

| # | Deliverable                                                                                                                                                                                                                      | Gate                                                                                                                                                                                                                                 |
| - | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 0 | `run.py` (venv, dependencies, ports, browser), the two-server process, job runner and scheduler, SQLite + Alembic, `/api/v1/health` + `/api/v1/system/capabilities`, Next.js static-export shell served by FastAPI, tesseract.js assets bundled | Starting from no`.venv`, `run.py` gets to a rendered page; `/api/v1/system/capabilities` shows a tiny Prophet fit and scikit-learn working                                                                                                   |
| 1 | Data model, auth, categories/aliases/rules, seed generator, renderers and samples, model training, demo bootstrap skeleton                                                                                                       | Demo login works; the generator gives identical output every run; pytest green                                                                                                                                                       |
| 2 | Consent API, capture pipeline, imports, simulators, review API, categorization and anomalies, background jobs                                                                                                                    | 24 months ingested.**No transactions from OTP or promo messages.** Amount and direction are extracted exactly right for ≥98% of known formats and ≥90% of held-out formats. Deduplication precision ≥0.98 and recall ≥0.95 |
| 3 | UI: auth/demo, shell, onboarding, dashboard, transactions and CSV wizard, connections and simulators, review                                                                                                                     | Playwright: demo login → a simulated SMS becomes a transaction → an OTP is ignored → review                                                                                                                                       |
| 4 | `/scan` with OCR in the browser, receipt parse and commit, PDF bills                                                                                                                                                           | Sample receipts are extracted above the accuracy threshold in headless Chromium; a receipt enriches its card transaction                                                                                                             |
| 5 | Forecasting, backtest, projection, what-if and`/forecast`                                                                                                                                                                      | The backtest table renders and the result is reported honestly; the fallback path is tested                                                                                                                                          |
| 6 | Subscriptions, tax (with PDF/CSV export) and their pages                                                                                                                                                                         | The seeded hike, dormant gym, overlap and trial are all detected; tax unit tests pass for both years                                                                                                                                 |
| 7 | Insights, coach, budgets and goals                                                                                                                                                                                               | Every intent answers from real data, and the fallback works                                                                                                                                                                          |
| 8 | Demo store, crawler, catalog, affordability, picks,`/picks`, and the insight and coach hooks                                                                                                                                   | BlockedMart is skipped because of robots.txt. A Hypothesis test shows no`buy_now` ever breaks the buffer or goal rules. Precision@10 beats the baseline                                                                            |
| 9 | Hardening: model-quality page, automatic demo refresh, README (one command, demo script, architecture, measured results), the full E2E suite, and updating the plan doc to match the build                                       | A cold start with fresh runtime data passes the full E2E; screenshots of every page reviewed                                                                                                        |

## Verification

- **After every phase:** `python3 run.py`, then `python3 run.py test`, then an API smoke script, then Playwright screenshots of the new pages, which I inspect.
- **At the end:**
  1. A cold start, timed until the app is ready.
  2. The full E2E suite.
  3. The demo script, walked from start to finish:
     1. Try the demo → dashboard → connections.
     2. Simulate a Swiggy SMS and then its order email. Check they become one transaction with line items.
     3. Send an OTP and check it's ignored.
     4. Revoke a source and delete its data.
     5. Scan a sample receipt.
     6. Check the forecast table, the subscriptions and the tax comparison.
     7. Ask the coach "can I afford …".
     8. Check the `/picks` tiers and the what-if, then press *Crawl now* and see the robots.txt skip.
     9. Reset the demo.
- **Measured results** go into the README and the model-quality page:
  - classifier F1;
  - extraction accuracy;
  - deduplication precision and recall;
  - OCR accuracy;
  - Prophet vs baseline;
  - precision@10.
- **Limits:** the original target run was macOS; a Windows x64 run was also verified on Python 3.11.9. Linux remains untested.

## Build status and verification (11 October 2026)

The feature implementation and planned frontend routes are present. Verification below was run on Windows x64 with Python 3.11.9 and Node 22.22.0.

- **Backend:** `py -3.11 run.py test` — 59 passed in 94.59 seconds.
- **End-to-end:** `npx playwright test` — 14 passed in 3.1 minutes, including registration/onboarding, SMS and email reconciliation, OTP rejection, browser OCR receipt attachment, review, forecasting, subscriptions, tax export, coach, Smart Picks crawl/robots.txt, source deletion and demo reset.
- **Cold-start data setup:** started the app using a fresh, isolated `FINPILOT_DATA_DIR` and alternate ports, without deleting the existing `.venv` or user data. The demo bootstrap, model training and bundled-store crawl completed; `/api/v1/health` returned `ok`, and `/api/v1/system/capabilities` reported Prophet and scikit-learn working. This verifies a fresh data directory, but not a clean dependency installation from an absent `.venv`.
- **OCR assets:** the generated static site contains the worker, WASM core variants and English trained data under `frontend/out/ocr`. The browser E2E receipt test passed on Windows.
- **Page review:** screenshots of login, register, onboarding and all 12 app pages were captured in `e2e/shots-review/`; the capture script reported no browser errors. The overview is `e2e/shots-review/contact.png`.
- **Test corrections:** the receipt E2E check now compares against the regenerated sample’s matched payment rather than a fixed amount. E2E setup resets the demo first so reruns start with clean seeded data. The Smart Picks check now verifies the crawl summary shown by the current UI.
- **Remaining verification:** the launcher’s first-time dependency installation from a machine with no `.venv` was not repeated; the current Windows environment already had its virtual environment. Linux is still untested. README benchmark figures remain the project’s reported measurements and were not all independently recomputed in this run.

## Sources

- Budget 2026 kept the slabs unchanged for FY 2026-27: [Storyboard18](https://storyboard18.com/special-coverage/budget-2026-no-change-in-tax-rates-in-budget-2026-rebate-continues-for-income-up-to-%e2%82%b912-lakh-88610.htm)
- The Income-tax Act 2025 took effect on 1 April 2026: [TaxGuru](https://taxguru.in/income-tax/income-tax-act-2025-force-1st-april-2026.html), [CalcGuru](https://calcguru.in/section-80c-now-section-123-deductions-fy-2026-27/)
- DPDP Rules: [Hogan Lovells](https://www.hoganlovells.com/en/publications/indias-digital-personal-data-protection-act-2023-brought-into-force-)
- TRAI SMS header suffixes: [MediaNama](https://www.medianama.com/2025/05/223-suffixes-commercial-sms-headers-spam/)
