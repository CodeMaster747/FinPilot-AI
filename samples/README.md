# Sample files

Synthetic files in the formats FinPilot imports, for trying the imports and receipt scanning in a browser without
using your own messages, and as fixtures for the end-to-end tests (`e2e/tests/new-user.spec.ts`). They were
generated from the demo persona (Aarav Sharma); the people, accounts and amounts are made up. On a phone you don't
need them: the Android app reads your real SMS inbox.

| File | Try it in | What it shows |
|---|---|---|
| `imports/sms_backup.xml` | Connections → Bank & payment SMS → Import a file | An Android *SMS Backup & Restore* export (302 messages, 11 July – 10 October 2026): bank alerts mixed with OTPs, promotions and personal chats; only the financial ones are kept |
| `imports/sms_messages.csv` | the same | The same kind of messages as a CSV export (date, sender, message) |
| `imports/inbox.mbox` | Connections → Receipts & bank emails → Import a file | A mailbox archive (as from Google Takeout): receipts, bills and bank alerts plus newsletters that are ignored |
| `imports/hdfc_statement.csv` | Transactions → Import statement | A bank statement; rows already captured from SMS or email are recognised and skipped |
| `receipts/nilgiris.png` | Scan a receipt | A supermarket receipt, matching an ₹818 card payment in `sms_backup.xml` |
| `receipts/decathlon-photo.jpg` | Scan a receipt | A tilted, noisy phone photo (straightened automatically) |
| `receipts/a2b-cash.png` | Scan a receipt | A restaurant bill paid in cash |
| `receipts/act-invoice.pdf` | Scan a receipt | A digital PDF bill (read from its text layer, no OCR needed) |

Imports respect the backfill window you chose when allowing the source: messages older than it are skipped.
