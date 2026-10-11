"""Hand-written messages in formats that never appear in the synthetic training data: other banks,
wallets, card issuers, billers and merchants. Used as a development set while building the
parsers; ``sealed_set.py`` holds a separate set written after the parsers were frozen."""

from __future__ import annotations

from datetime import datetime

from app.services.ingestion.types import RawMessage

T = datetime(2026, 10, 9, 10, 0)

# (channel, sender, subject, body, kind, amount, direction)
CASES: list[tuple[str, str, str | None, str, str, str | None, str | None]] = [
    ("sms", "VM-AXISBK-S", None, "INR 250.00 debited\nA/c no. XX3201\n09-10-26, 13:45:10\nUPI/P2M/627814567890/ZOMATO\nNot you? SMS BLOCKUPI Cust ID to 919951860002\nAxis Bank", "transaction", "250.00", "debit"),
    ("sms", "JD-KOTAKB-S", None, "Sent Rs.1499.00 from Kotak Bank AC X1123 to amazonpay@apl on 08-10-26.UPI Ref 627712345678. Not you, kotak.com/fraud", "transaction", "1499.00", "debit"),
    ("sms", "JD-KOTAKB-S", None, "Received Rs.5000.00 in your Kotak Bank AC X1123 from ravi.k@okhdfcbank on 07-10-26.UPI Ref:627687654321.", "transaction", "5000.00", "credit"),
    ("sms", "BZ-IDFCFB-S", None, "Your A/C XXXXXXX4482 has been debited with INR 799.00 on 05-OCT-2026 towards UPI/627512398745/Spotify India. Avl Bal INR 21,340.50 - IDFC FIRST Bank", "transaction", "799.00", "debit"),
    ("sms", "AD-PNBSMS-S", None, "Your A/c XX7781 debited INR 2,000.00 on 04-10-26 18:22:11 Thru ATM Cash Wdl. Avl Bal INR 12,445.20 -PNB", "transaction", "2000.00", "debit"),
    ("sms", "VM-CANBNK-S", None, "An amount of INR 1,250.00 has been DEBITED to your account XXX1234 on 03/10/2026 towards UPI P2M payment to BIGBASKET. Total Avail.bal INR 45,600.00. - Canara Bank", "transaction", "1250.00", "debit"),
    ("sms", "JM-BOBTXN-S", None, "Rs.3500.00 Credited to A/c ...6789 thru UPI/627312345678 by ANITHA S. Total Bal:Rs.15400.00CR. Avlbl Amt:Rs.15400.00(04-10-2026 10:32:11) - Bank of Baroda", "transaction", "3500.00", "credit"),
    ("sms", "VK-YESBNK-S", None, "INR 3,250.00 spent on YES BANK Card X5566 @SWIGGY on 02-10-2026 08:42:15 PM. Avl Lmt: INR 87,450.00. Not you? Call 18001200", "transaction", "3250.00", "debit"),
    ("sms", "AD-AMEXIN-S", None, "Alert: You've spent INR 12,345.00 on your AMEX card ** 31007 at FLIPKART on 1 October 2026 at 09:15 PM IST.", "transaction", "12345.00", "debit"),
    ("sms", "VM-SBICRD-S", None, "Rs.2,999.00 spent on your SBI Credit Card ending 4417 at MYNTRA on 30/09/26. Trxn. not done by you? Report at sbicard.com", "transaction", "2999.00", "debit"),
    ("sms", "BZ-INDUSB-S", None, "Your IndusInd Bank Debit Card XX2211 has been used for INR 1,180.00 at RELIANCE SMART on 29-09-2026 19:12. Avl Bal INR 32,100.40", "transaction", "1180.00", "debit"),
    ("sms", "AD-HDFCBK-S", None, "Thank you for using your HDFC Bank Credit Card ending 7731 for Rs 4,520.00 at CROMA on 2026-09-28:14:05:33. Authorization code:- 012345", "transaction", "4520.00", "debit"),
    ("sms", "JD-ICICIB-S", None, "ICICI Bank Acct XX812 debited for Rs 340.00 on 27-Sep-26; RAPIDO credited. UPI:627012345678. Call 18002662 for dispute. SMS BLOCK 812 to 9215676766.", "transaction", "340.00", "debit"),
    ("sms", "JD-ICICIB-S", None, "Dear Customer, Acct XX812 is credited with Rs 15,000.00 on 26-Sep-26 from PRIYA K. UPI:626912345678-ICICI Bank.", "transaction", "15000.00", "credit"),
    ("sms", "VM-FEDBNK-S", None, "Rs.650.00 debited from your A/c XX9012 on 25-09-2026 for UPI txn to UBER INDIA. UPI Ref 626812345678. Bal Rs.8,240.00 - Federal Bank", "transaction", "650.00", "debit"),
    ("sms", "VM-PAYTMB-S", None, "Rs 120 paid to Chennai Metro Rail from Paytm Payments Bank A/c XX8899. UPI Ref: 626712345678. Balance: Rs 2,430", "transaction", "120.00", "debit"),
    ("sms", "AX-UNIONB-S", None, "A/c *4433 Debited for Rs:1500.00 on 24-09-2026 18:20:15 by Mob Bk ref no 626612345678 Avl Bal Rs:21000.50.If not you, Call 1800222243 -Union Bank of India", "transaction", "1500.00", "debit"),
    ("sms", "VM-AUBANK-S", None, "Dear Customer, Your A/c XX0091 is credited with INR 85,000.00 on 30-09-2026 by NEFT from ACME SOFTWARE PVT LTD. Avl Bal INR 1,02,334.00 - AU Bank", "transaction", "85000.00", "credit"),
    ("sms", "VM-HDFCBK-S", None, "Money Transferred - Rs 5,000.00 from HDFC Bank A/c **4521 to A/c **7712 on 23-09-26. Ref no 626512345678. Not you? Call 18002586161", "transaction", "5000.00", "debit"),
    ("sms", "VM-SBIINB-S", None, "Dear SBI Customer, Rs.3000 withdrawn at SBI ATM S1NC000123401 from A/c X9034 on 22Sep26 Transaction Number 4789. Available Balance Rs.41,890. If not withdrawn by you, call 1800111109", "transaction", "3000.00", "debit"),
    ("sms", "VM-HDFCBK-S", None, "Refund of Rs.499.00 for your Swiggy order 1234567 has been credited to your HDFC Bank A/c XX4521 on 05-10-26.", "refund", "499.00", "credit"),
    ("sms", "VM-SBICRD-S", None, "Dear Customer, INR 1,299.00 refunded to your SBI Credit Card ending 4417 by AMAZON on 04/10/26.", "refund", "1299.00", "credit"),
    ("sms", "VM-AXISBK-S", None, "Transaction of Rs.560.00 to ZEPTO failed due to technical error. Amount debited, if any, will be refunded within 5 days. - Axis Bank", "failed_or_reversed", None, None),
    ("sms", "JD-KOTAKB-S", None, "Dear Customer, Rs.890.00 has been reversed to your A/c XX1123 for txn UPI Ref 626412345678 dated 20-09-26. -Kotak Bank", "failed_or_reversed", None, None),
    ("sms", "JD-ICICIB-S", None, "Your payment of Rs 1,050.00 to IRCTC could not be completed. Amount will be auto-reversed. -ICICI Bank", "failed_or_reversed", None, None),
    ("sms", "VM-AXISBK-T", None, "Your OTP for transaction of INR 4,999.00 at AJIO on Axis Bank card XX7766 is 482910. Valid for 3 mins. Do not share it with anyone - Axis Bank", "otp", None, None),
    ("sms", "JD-KOTAKB-T", None, "238761 is your one-time password to login to Kotak Net Banking. Never share it.", "otp", None, None),
    ("sms", "VM-SBIINB-T", None, "Dear Customer, 774512 is the OTP to complete your payment of Rs.1,200.00 at PhonePe. OTP valid for 5 minutes. Do not share. -SBI", "otp", None, None),
    ("sms", "VM-SWIGGY-T", None, "Use verification code 553201 to verify your mobile number on Swiggy. Do not share this code.", "otp", None, None),
    ("sms", "JD-KOTAKB-S", None, "Get an instant Personal Loan of up to Rs.10,00,000 at 10.5% p.a. Apply in 2 minutes: kotak.com/pl", "promo", None, None),
    ("sms", "VK-FLPKRT-S", None, "Big Billion Days are here! Up to 80% off + extra Rs.1,000 off with Axis cards. Shop now on Flipkart.", "promo", None, None),
    ("sms", "VM-JIOINF-S", None, "Recharge with Rs.299 and get 2GB/day + unlimited calls for 28 days. Recharge now on MyJio app.", "promo", None, None),
    ("sms", "AD-ICICIB-S", None, "Congratulations! You are eligible for a credit card limit upgrade to Rs.2,50,000. Reply YES to accept.", "promo", None, None),
    ("sms", "BZ-ZOMATO-S", None, "Zomato Gold is back! Get free delivery + up to 30% off at 20,000+ restaurants for just Rs.30/month", "promo", None, None),
    ("sms", "VM-BESCOM-S", None, "Dear Customer, your BESCOM electricity bill for RR No. 1234567 is Rs.1,342.00. Due date: 15-10-2026. Pay via BESCOM app.", "bill_due", "1342.00", None),
    ("sms", "VM-JIOINF-S", None, "Your Jio Postpaid bill of Rs.599.00 for 9876543210 is generated. Due date 20-Oct-2026. Pay on MyJio.", "bill_due", "599.00", None),
    ("sms", "AD-TATAPW-S", None, "Tata Power: Bill amount Rs.2,145 for CA No 60012345 due on 18/10/2026. Pay online to avoid late fee.", "bill_due", "2145.00", None),
    ("sms", "VM-VFIDEA-S", None, "Vi Postpaid: Your bill of Rs 449.00 is due on 12-Oct-2026. Pay now using Vi App.", "bill_due", "449.00", None),
    ("sms", "VM-SBICRD-S", None, "Your SBI Card statement for card ending 4417 is generated. Total Amt Due: Rs 18,450.00, Min Amt Due: Rs 925.00, Due Date: 25-Oct-26.", "statement", "18450.00", None),
    ("sms", "VM-AXISBK-S", None, "Axis Bank Credit Card XX7766 statement: Total due INR 9,870.45. Minimum due INR 500.00. Pay by 22-10-2026.", "statement", "9870.45", None),
    ("sms", "VM-AXISBK-S", None, "Your A/c XX3201 balance as on 08-10-2026 is INR 54,321.00. - Axis Bank", "balance", None, None),
    ("sms", "JD-KOTAKB-S", None, "Avl Bal in your Kotak Bank AC X1123 is Rs.12,880.50 as of 08-10-26 10:00 AM.", "balance", None, None),
    ("sms", "VM-SWIGGY-S", None, "Your Swiggy order is out for delivery! Track it here: swig.gy/t/abc", "other", None, None),
    ("sms", "VM-HDFCBK-S", None, "Your KYC is due for update. Please visit the nearest branch or update via NetBanking.", "other", None, None),
    ("sms", "VM-SBIINB-S", None, "Dear Customer, your cheque book request for A/c X9034 has been registered.", "other", None, None),
    ("email", "Swiggy Instamart <noreply@swiggy.in>", "Your Instamart order is delivered", "Your Instamart order is delivered!\nItems: Milk x2, Bread x1, Eggs x1\nBill Total: ₹642.00\nPaid via UPI", "order_receipt", "642.00", None),
    ("email", "Zepto <no-reply@zepto.co>", "Order #ZP123456 delivered", "Order #ZP123456 delivered.\nGrand Total ₹386.00\nThanks for ordering with Zepto", "order_receipt", "386.00", None),
    ("email", "Blinkit <noreply@blinkit.com>", "Your Blinkit order summary", "Here is your order summary.\nTotal ₹1,045.00\nDelivered in 9 minutes", "order_receipt", "1045.00", None),
    ("email", "Flipkart <noreply@flipkart.com>", "Refund initiated for your order", "Refund of ₹2,499.00 has been initiated for your order OD432109876543210 to your original payment method.", "refund", "2499.00", "credit"),
    ("email", "Spotify <no-reply@spotify.com>", "An update to your Premium plan price", "Your Premium Individual plan price will change from ₹119/month to ₹139/month starting 01 Nov 2026.", "subscription_notice", None, None),
    ("email", "YouTube <noreply-youtube@youtube.com>", "Your YouTube Premium trial is ending", "Your YouTube Premium free trial ends on 20 October 2026. After that you'll be charged ₹149/month.", "subscription_notice", None, None),
    ("email", "Airtel <ebill@airtel.com>", "Airtel bill reminder", "Hi, your Airtel Xstream Fiber bill of Rs. 799.00 is due on 25 Oct 2026. Pay now to avoid late fee.", "bill_due", "799.00", None),
    ("email", "Axis Bank Alerts <alerts@axisbank.com>", "Transaction alert", "Dear Customer, INR 2,150.00 spent on your Axis Bank Credit Card XX7766 at DMART on 07-10-2026 18:30:12. Available limit INR 1,02,850.00.", "transaction", "2150.00", "debit"),
    ("email", "HDFC Bank InstaAlerts <alerts@hdfcbank.net>", "Account credited", "Dear Customer, Rs.15,000.00 has been credited to your account **4521 by IMPS from PRIYA K on 06-10-26. Ref 626912345111.", "transaction", "15000.00", "credit"),
    ("email", "MakeMyTrip <noreply@makemytrip.com>", "Booking confirmed - Chennai to Goa", "Your flight booking is confirmed. Booking ID NF2K9X81\nTotal amount paid: ₹8,245.00", "order_receipt", "8245.00", None),
    ("email", "BookMyShow <tickets@bookmyshow.com>", "Your tickets are booked!", "Booking ID WXYZ1234\n2 tickets for the 7:30 PM show\nTotal Amount ₹560.00", "order_receipt", "560.00", None),
    ("email", "IRCTC <ticketadmin@irctc.co.in>", "Booking Confirmation on IRCTC, Train: 12608", "PNR 4512345678\nTotal Fare (all inclusive): ₹1,215.00", "order_receipt", "1215.00", None),
    ("email", "Amazon.in <store-news@amazon.in>", "Deals of the day: up to 70% off on headphones", "Up to 70% off on top headphone brands. Limited time deals, shop now!", "promo", None, None),
    ("email", "Axis Bank <cc.statements@axisbank.com>", "Your Axis Bank Credit Card statement", "Your statement is ready.\nTotal Amount Due ₹9,870.45\nMinimum Amount Due ₹500.00\nPayment Due Date 22 Oct 2026", "statement", "9870.45", None),
    ("email", "cult.fit <no-reply@cult.fit>", "Session confirmed", "Your HRX Workout session is confirmed for Sat, 10 Oct 2026, 7:00 AM at Cult Velachery.", "usage", None, None),
    ("email", "Decathlon <ereceipt@decathlon.in>", "Your Decathlon e-receipt", "Thank you for shopping at Decathlon Velachery.\nTotal: ₹2,748.00\nPayment: Card", "order_receipt", "2748.00", None),
    ("email", "Netflix <info@account.netflix.com>", "Your Netflix membership has been renewed", "Your membership has been renewed. Amount charged: ₹649.00 to your card ending 7788.", "order_receipt", "649.00", None),
    ("email", "Amazon.in <shipment-tracking@amazon.in>", "Your package has shipped", "Your Amazon order #405-1234567-1234567 has been shipped and will arrive Friday.", "other", None, None),
]


def messages() -> list[RawMessage]:
    out = []
    for i, (channel, sender, subject, body, kind, amount, direction) in enumerate(CASES):
        out.append(RawMessage(channel=channel, sender=sender, received_at=T, subject=subject, body=body,
                              html=f"<html><body><p>{body}</p></body></html>" if channel == "email" else None,
                              truth={"kind": kind, "template": f"challenge_{i}", "txn_id": None,
                                     "expect": {k: v for k, v in (("amount", amount), ("direction", direction)) if v}}))
    return out
