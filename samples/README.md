# Sample files

Files for trying FinPilot's imports and receipt scanning with your own (non-demo) account. They are generated
from the demo persona — the app creates fresh copies, dated up to the current day, every time the demo is
built, and offers them in the app itself (Connections → Import a file, Transactions → Import statement, Scan a receipt).

| File | Try it in | What it shows |
|---|---|---|
| `imports/sms_backup.xml` | Connections → Bank & payment SMS → Import a file | An Android "SMS Backup & Restore" export: bank alerts mixed with OTPs, promotions and personal chats (only the financial ones are kept) |
| `imports/sms_messages.csv` | the same | The same kind of messages as a CSV export (date, sender, message) |
| `imports/inbox.mbox` | Connections → Receipts & bank emails → Import a file | A mailbox archive (as from Google Takeout): receipts, bills and bank alerts plus newsletters that are ignored |
| `imports/hdfc_statement.csv` | Transactions → Import statement | A bank statement; rows already captured from SMS/email are recognised and skipped |
| `receipts/nilgiris.png` | Scan a receipt | A supermarket receipt |
| `receipts/decathlon-photo.jpg` | Scan a receipt | A tilted, noisy phone photo (straightened automatically) |
| `receipts/a2b-cash.png` | Scan a receipt | A restaurant bill paid in cash |
| `receipts/act-invoice.pdf` | Scan a receipt | A digital PDF bill (read from its text layer, no OCR needed) |

The people, accounts and amounts are synthetic.
