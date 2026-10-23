# FinPilot AI

A personal-finance assistant for India that builds your financial picture from **your own bank SMS and email**:
an Android app reads the bank and payment alerts in your phone's inbox, a mailbox connection reads bank and shop
emails, and everything is processed by a FinPilot server running on your own laptop. Each source is read only after
you allow it. Receipts, bills, bank statements and manual entries fill in the rest.

Sem VII Full Stack Development project, SSN College of Engineering:
Jeya Sangavi R · Rahul Akshath Rajendran · Rakshitha S

---

## Use it with your own phone

You need a laptop with **Python 3.11+** and an **Android phone** (Android 8 or newer). Building the app also needs
**Node.js 22+**, **JDK 21** and the **Android SDK** (installing Android Studio provides the last two).

1. **Start the server on the laptop:**
   ```bash
   python3 run.py          # Windows: py run.py
   ```
   The first run creates `.venv`, installs the pinned packages (internet needed once, a few minutes), sets up the
   database and trains the models. It then prints the addresses the phone can use and a **QR code**. If the laptop
   asks whether Python may accept incoming connections, allow it.
2. **Install the app.** On the phone, turn on *Developer options → USB debugging* (tap *Build number* seven times
   to unlock Developer options; Xiaomi/Redmi/POCO also need *Install via USB*). Connect it by USB and run:
   ```bash
   python3 run.py install-android
   ```
   This builds the app the first time (`build-android`) and installs it with `adb`. Installing over USB matters:
   in India, Play Protect blocks apps that read SMS when they are sideloaded from a browser or a messaging app.
3. **Pair and sign up.** Open **FinPilot AI** on the phone, scan the QR code (or type the address), and
   **create an account**. Phone and laptop must be on the same Wi-Fi, or the laptop on the phone's hotspot.
   Networks that isolate devices (most college Wi-Fi) need `python3 run.py --tunnel`, which publishes the server
   at a `https://….trycloudflare.com` address (install `cloudflared` first).
4. **Set up** (each step can be skipped):
   - **About you:** take-home pay and payday, rent and landlord, city. FinPilot learns these from your messages
     over time; entering them makes the plan useful from day one.
   - **Bank & payment SMS:** read the notice, choose how far back to read (default 12 months) and allow. Android
     then asks for the SMS permission. The app reads the inbox month by month, **filters on the phone** (personal
     chats, `-P` promotions and OTP-only texts never leave it) and uploads only bank and payment alerts.
   - **Email:** connect Gmail, Yahoo, Zoho, iCloud or any IMAP mailbox with an **app password**. Only emails from
     known banks, card issuers, shops and billers are opened, nothing is marked read, and the password is stored
     encrypted.
5. **Use it.** The dashboard shows your accounts and balance, safe-to-spend, spending, upcoming bills and the
   forecast. New SMS are picked up while the app is open: when it opens or comes back to the foreground, and every
   minute. Email is checked every 30 minutes while the server runs, or on *Sync now*.

Everything also works in a browser on the laptop (http://localhost:8000), except reading SMS. A browser can instead
import an *SMS Backup & Restore* XML or CSV file exported from the phone.

| Command | What it does |
|---|---|
| `python3 run.py` | Start the server (and open the browser) |
| `python3 run.py --no-browser` | Start without opening a browser |
| `python3 run.py --tunnel` | Also publish the server through a Cloudflare quick tunnel, for networks the phone can't reach directly |
| `python3 run.py --local-only` | Listen on this computer only (the phone can't connect) |
| `python3 run.py build-android` | Build the Android app (`frontend/android/app/build/outputs/apk/debug/app-debug.apk`) |
| `python3 run.py install-android` | Install it on a phone connected by USB |
| `python3 run.py reset` | Delete **all** local data (every account) and rebuild the demo |
| `python3 run.py test` | Run the backend tests |
| `python3 run.py build-frontend` | Rebuild the web app (only for UI development) |

### The demo account

The login page also offers **Explore the demo account (sample data)**: a made-up person, Aarav Sharma, with 24 months
of synthetic messages ending today. It exists so that every analysis (a full forecast backtest, dormant
subscriptions, two tax years) can be shown at once. It is labelled as sample data on every page, it can't connect
SMS, email or file imports, and real accounts never receive any of its data. Sign-in, if asked:
`demo@finpilot.ai` / `demo1234`.

---

## What it does

**Consent, per source.** SMS and email are separate sources. Nothing is read until you allow one in a dialog that
shows what is read, what is never read, what is stored and for how long, and what FinPilot will never do. You choose
the backfill window, and can pause, resume, revoke or delete a source's data at any time. Revoking email deletes the
stored mailbox password. Every change is recorded with the notice version and its hash. The design follows the
consent principles of India's DPDP Act 2023; it does not claim compliance.

**Where data comes from:**
- **Phone SMS** (Android app): a native plugin reads the SMS inbox, filters on the device and uploads only financial
  alerts to `POST /api/v1/ingest/sms/device`. Each SMS has one identity (sender, time, text), so a message synced
  from the phone and the same message imported from a backup file are stored once.
- **Mailbox** (IMAP + app password): Gmail is searched in *All Mail* for allowlisted senders (any `*.bank.in`
  domain, card issuers, UPI apps, shops, telecom, utilities, insurers, AMCs and RTAs, plus domains you add); other
  providers by date and sender. Sync is incremental (UIDVALIDITY/UID).
- **Files:** an *SMS Backup & Restore* XML, CSV or pasted text; `.eml` or `.mbox` email; bank statements in
  **CSV, XLSX or XLS** with a column-mapping wizard (a balance column sets the account's balance).
- **Receipts:** a camera photo (in the app) or an image is read **on the device** with tesseract.js; digital PDF
  bills are read from their text layer. An unpaid bill's due date can be saved as an upcoming payment.
- **Manual entry**, with your own accounts (savings, credit card, cash, wallet) and their current balances.

**One pipeline for every feed:**
1. **Pre-filter:** promotional DLT headers (`-P`), personal numbers and non-allowlisted email senders are dropped
   before anything is stored.
2. **Classify** into 12 message kinds (TF-IDF + logistic regression). OTPs are never stored, and a message with an
   amount, a money verb and an account, card or UPI marker is never silently dropped: at worst it goes to Review.
3. **Extract** amount, direction, account, payee or UPI ID, reference, date and balance: per-bank templates first,
   then a generic extractor. Times are converted to Indian time (`FINPILOT_TZ`).
4. **Reconcile:** one transaction per real payment across SMS, email and files; own-account transfers and card bill
   payments are paired so they don't count as spending; reversals and refunds are linked; an email receipt waits up
   to three days for its bank SMS before it is recorded on its own.
5. **Categorise:** your rules, then known merchants, then the ML model. Credits are never put in expense categories
   (salary, interest, transfers and refunds are handled separately). Uncertain items go to **Review**, and your
   answers become rules.

Raw message text is encrypted (Fernet) and deleted after 90 days; extracted fields are kept.

**Analysis on your data:**
- **Balance and safe-to-spend:** balances come from "Avl Bal" in alerts, statements or what you enter. Income uses
  only months your data covers, falling back to the take-home pay you entered. Safe-to-spend never dips into the
  safety buffer, upcoming bills or goal savings.
- **Forecast:** your recurring schedule (salary, rent, EMIs, SIPs, subscriptions, bills, including ones you entered
  before they repeat three times) plus a model of day-to-day spending: a seasonal baseline until there are 120 days
  of history, then Prophet. It shows an 80% band, a what-if, and a low-balance warning only when the balance is known.
- **Anomalies:** unusual amounts per merchant, duplicate charges and large spends at new merchants (after your first
  60 days, so a fresh import doesn't flag everything).
- **Subscriptions:** repeating amounts, UPI AutoPay / e-mandate / standing-instruction debits and known subscription
  services; price rises, overlaps, and (when emails show it) dormant subscriptions and trials that became paid.
- **Tax:** new vs old regime for FY 2025-26 and Tax Year 2026-27 from your salary details (gross, basic, HRA, rent,
  city, PF, TDS) and the deductions found in your payments; HRA uses the metro list for each year; advance tax only
  once TDS is entered. CSV and PDF export (shared from the phone).
- **Wishlist:** things you want, with a price or a product link. Prices are read from stores that publish structured
  prices and allow it in robots.txt, and re-checked daily; otherwise you enter the price. Each item is placed in
  *Buy now*, *For your goals*, *Save up for* or *Not yet* against your real budget, and can become a goal.
- **Budgets & goals**, an **insight feed**, and a **coach** that answers questions (spending, bills, goals, tax,
  "can I afford…") from the same numbers as the pages. It is an intent classifier with computed answers; no outside
  AI service is used.

---

## Measured results

Measured on 18 October 2026 on this machine (macOS, Apple Silicon, Python 3.14). The model figures are shown live in
**Settings → Model evaluation**. The demo persona is regenerated for the current date, so its counts and forecast errors
shift slightly from day to day.

| What | Result |
|---|---|
| Real-format corpus: 90 hand-written messages in the formats of 25+ banks, card issuers, payments banks, billers and AMCs (type / amount / direction / account / payee) | 100% on every field · 0 money messages dropped · 0 OTPs stored |
| Hand-written challenge set (63 messages, other banks and merchants): type / amount / direction | 98.3% / 100% / 100% |
| Unseen bank styles (Axis, Kotak; 200 synthetic messages): type / amount / direction | 100% / 100% / 100% |
| Message type, held-out synthetic test split (1,070 messages), macro F1 | 100% |
| Demo persona, 1,542 payments across SMS + email: one record per payment (precision / recall) | 100% / 100% |
| Own-account transfers found / false transfers | 100% / 0 |
| Category accuracy on the demo's captured payments | 99.8% (3 deliberately ambiguous payees, sent to Review) |
| Email receipts attached to the right payment (552) | 100% |
| Category model on freshly generated noisy merchant names (24 classes) | 92.1% accuracy, 92.2% macro F1 |
| Coach intent on held-out paraphrases (26) | 84.6% |
| Forecast, mean absolute daily error over 6 rolling 30-day backtests (demo persona) | Seasonal naive ₹9,784 · + known schedule ₹5,771 · **Prophet + known schedule ₹5,746** |
| Backend tests (pytest + Hypothesis) | 82 passed |
| End-to-end tests (Playwright): a new user's full journey on real files, the phone layout on 12 pages (Pixel 7), the demo | 23 passed |
| The Android app on an Android 15 emulator (`e2e/android-smoke.mjs`): pair, sign up, SMS consent and Android's permission dialog, on-phone filtering, one transaction per bank alert, a new SMS picked up while the app is open, the back button, sharing a PDF, signing out and in | 17 of 17 checks passed |

**Reading these honestly.**
- **The real-format corpus is a regression set, not an unseen test.** It was written from the published alert
  formats of real institutions and used while improving the extractor, so its 100% shows those formats are handled,
  not how an unknown inbox will do. Your own inbox will contain formats it lacks; those go to **Review** (never
  silently dropped), and *Connections → Capture health* shows how many did.
- **All the other message figures are on synthetic data** with known answers. The models are trained on synthetic
  data only.
- **Forecast:** knowing the schedule cuts the error by about 41% against the seasonal baseline; Prophet adds only a
  little on top (0.4% on 18 October, 1.7% on 17 October). An earlier version of this README claimed 85%: that
  backtest detected the schedule from data after the forecast date, which leaked the future. Each fold now detects it
  from its own training window only. WAPE is used rather than MAPE because daily net cash flow often crosses zero.
- **The phone path is tested on an emulator,** with real-format bank SMS, an OTP, a promotion, a personal chat and an
  alert older than the consent window planted in its inbox. An emulator can't show phone makers' own SMS rules
  (Xiaomi's "notification SMS" permission, "restricted settings"); the app detects those cases and explains the fix.

---

## How it is built

```
Android phone: FinPilot AI (Capacitor 8 wrapping the same Next.js UI, bundled in the APK)
 ├─ SmsInbox plugin (Java, READ_SMS) → filter on the phone → POST /api/v1/ingest/sms/device
 ├─ Camera → tesseract.js OCR in the app → /api/v1/receipts/parse
 ├─ Preferences (server address, tokens) · Filesystem + Share (CSV/PDF/JSON exports) · barcode scanner (pairing)
 └─ HTTP(S) with Bearer tokens ──────────────┐
                                             ▼
Laptop: python3 run.py → one Python process, FastAPI on 0.0.0.0:8000 (+ optional Cloudflare tunnel)
 ├─ /api/v1/* JSON API: cookie sessions + CSRF header for the browser, Bearer tokens for the app, CORS for the app only
 ├─ /*        the pre-built Next.js static site for the laptop browser
 ├─ job runner (threads) + scheduler: mailbox sync every 30 min, wishlist prices daily, nightly analytics, retention purge
 └─ SQLite in WAL mode (data/finpilot.db) via SQLAlchemy 2 + Alembic migrations
```

| Layer | Tools |
|---|---|
| Backend | FastAPI, Uvicorn, SQLAlchemy 2, Alembic, Pydantic 2, PyJWT, pwdlib (bcrypt), cryptography (Fernet), imaplib |
| ML & data | scikit-learn, Prophet, pandas, NumPy, rapidfuzz, dateparser |
| Documents & web | pdfplumber, ReportLab, openpyxl/xlrd, httpx, protego (robots.txt), BeautifulSoup + lxml, defusedxml, segno (QR) |
| Frontend | Next.js 16 (static export), React 19, TypeScript, Tailwind CSS 4, shadcn/ui on Base UI, TanStack Query, Recharts, tesseract.js |
| Android | Capacitor 8 (app, preferences, camera, filesystem, share, barcode scanner) and a local SMS plugin; minSdk 26, targetSdk 36 |
| Tests | pytest, Hypothesis, Playwright (browser, and Android through its WebView) |

**Decisions that keep it reliable.**
- **Money** is stored as integer paise and handled as `Decimal`, never floats.
- **Same UI everywhere:** the app bundles the static site; on the phone it calls the server address you paired, with
  Bearer tokens and a 90-day refresh token, instead of cookies.
- **targetSdk stays at 36:** Android 17 blocks local-network access by default for apps targeting SDK 37+, which
  would stop the app reaching the laptop over Wi-Fi.
- **Models train in seconds at first start,** so there are no binary model files to ship.
- **Receipt OCR runs on the device,** so the server needs no Tesseract or OpenCV.

```
FinPilot AI/
├─ run.py                 one-command launcher (server, Android build and install)
├─ backend/
│  ├─ app/
│  │  ├─ api/v1/          REST endpoints
│  │  ├─ services/        consent, ingestion (device SMS, IMAP, files), receipts, accounts, forecasting,
│  │  │                   subscriptions, tax, wishlist and price fetching, affordability, coach, insights
│  │  ├─ ml/              training, evaluation, the real-format corpus
│  │  ├─ seed/            the demo persona and its message renderers
│  │  ├─ models/ db/ core/ jobs/
│  ├─ alembic/            migrations
│  └─ tests/              82 tests
├─ frontend/              Next.js source; out/ is the pre-built site; android/ is the Capacitor project
├─ e2e/                   Playwright suites: browser (playwright.config.ts) and the Android app (android-smoke.mjs)
└─ samples/               files for trying the imports and receipt scanning
```

Runtime data (the database, uploads, trained models and the generated secret key) lives in `data/`, created on first
run.

---

## Testing

```bash
python3 run.py test                                   # backend: pytest + Hypothesis
cd frontend && npm run typecheck && npm run lint      # frontend
# Browser end-to-end, against a server on a throwaway data folder:
FINPILOT_DATA_DIR=/tmp/fp-e2e FINPILOT_PORT=8123 python3 run.py --no-browser
cd e2e && npm ci && npx playwright install chromium && FINPILOT_URL=http://localhost:8123 npx playwright test
# The Android app on an emulator with a "Google APIs" image (adb root is needed to plant SMS), same server:
python3 run.py build-android && npx playwright install android
cd e2e && FINPILOT_URL=http://localhost:8123 PHONE_URL=http://10.0.2.2:8123 node android-smoke.mjs
```

## Troubleshooting

- **The app says it can't reach the server:** check that `python3 run.py` is running and that the phone is on the same
  network (or the laptop is on the phone's hotspot). Allow Python through the laptop's firewall. On college or office
  Wi-Fi, restart with `--tunnel`. *Settings → Change server* in the app re-pairs.
- **Android shows SMS as a "Restricted setting":** open *App info → ⋮ → Allow restricted settings*, then
  *Permissions → SMS → Allow*. The app walks you through it.
- **Xiaomi, Redmi or POCO find no bank messages:** *Settings → Apps → FinPilot AI → Other permissions* → allow
  *Notification SMS* (sometimes *Service SMS*).
- **Gmail rejects the password:** it needs an **app password** (myaccount.google.com/apppasswords, with 2-Step
  Verification on), not your normal password.
- **Prophet can't run on a machine:** the forecast falls back to the baseline model and says so.
- **Start over:** `python3 run.py reset` deletes every local account and rebuilds the demo.

## Limits, stated plainly

- **Android only:** iOS gives apps no access to SMS.
- **The laptop must be running and reachable.** Plain local-network traffic is HTTP; use `--tunnel` for HTTPS or
  for networks that isolate devices.
- **New SMS are read while the app is open** (on open, on resume and every minute), not in the background.
- **Installing:** over USB with `adb`. Android 13+ may require "Allow restricted settings" once.
- **Unfamiliar formats:** a bank format not seen before goes to Review rather than being dropped, and a template can
  be added for it.
- **Wishlist prices** are read only from stores that publish structured prices and allow it; others take a manual price.
- **Email:** app passwords need 2-Step Verification. Outlook.com and Hotmail can't be connected (Microsoft allows only
  OAuth), and Workspace admins can disable app passwords.
- **Models are trained on synthetic data;** accuracy is reported on synthetic and hand-written test sets.
- **Planning tool, not tax advice.** The 2026-27 rules follow the Income-tax Act 2025 as announced.
- **Tested on macOS (Apple Silicon).** `run.py` is written to be cross-platform, but Windows and Linux were not
  tested.
