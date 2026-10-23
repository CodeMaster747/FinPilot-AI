"""A second hand-written evaluation set in the message formats Indian banks, card issuers, payment banks, billers and
merchants actually send (as of 2025–26), written separately from the training phrases and the challenge set, and
before the extractor changes it is used to measure. Each case also names the account digits and the payee a correct
reading must find, so it measures the whole extraction, not just the message type and amount.

Nothing here is used for training. A message with no payee label means "the alert doesn't name one".
"""

from __future__ import annotations

from datetime import datetime

from app.services.ingestion.types import RawMessage

T = datetime(2026, 10, 3, 21, 0)

# (channel, sender, subject, body, kind, amount, direction, mask, payee — a word the payee must contain)
CASES: list[tuple[str, str, str | None, str, str, str | None, str | None, str | None, str | None]] = [
    # --- SBI ---
    ("sms", "AD-SBIUPI-S", None, "Dear UPI user A/C X4417 debited by 120.0 on date 02Oct26 trf to CHENNAI METRO Refno 627512345671. If not u? call 1800111109. -SBI", "transaction", "120.00", "debit", "4417", "chennai metro"),
    ("sms", "JM-SBIUPI-S", None, "Dear SBI User, your A/c X4417-credited by Rs.2500 on 01Oct26 transfer from SURESH B Ref No 627412345672 -SBI", "transaction", "2500.00", "credit", "4417", "suresh"),
    ("sms", "VM-SBIINB-S", None, "Dear Customer, Your A/C XXXXX4417 has a credit by Transfer of Rs 62,500.00 on 30/09/26 by NEFT-ZETA TECH SOLUTIONS-SALARY. Avl Bal Rs 81,210.40-SBI", "transaction", "62500.00", "credit", "4417", "zeta"),
    ("sms", "VM-SBIINB-S", None, "Your A/C XXXXX4417 Debited INR 1,180.00 on 28/09/26 -Transferred to MR KRISHNA R. Avl Balance INR 79,020.40-SBI", "transaction", "1180.00", "debit", "4417", "krishna"),
    ("sms", "VM-ATMSBI-S", None, "Dear Customer, Rs.2000 withdrawn at SBI ATM S1BW012345601 from A/c X4417 on 27Sep26 Transaction Number 5521. Available Balance Rs.80,200. If not withdrawn by you, call 1800111109 -SBI", "transaction", "2000.00", "debit", "4417", None),
    ("sms", "VM-SBICRD-S", None, "Transaction of Rs.1,849.00 on your SBI Credit Card ending 9921 at DOMINOS PIZZA on 26/09/26. If not done by you, report at sbicard.com/Dispute", "transaction", "1849.00", "debit", "9921", "dominos"),
    ("sms", "VM-SBIINB-S", None, "Dear Customer, Interest of Rs.1,234.00 has been credited to your A/c XXXXX4417 on 30/09/2026 -SBI", "transaction", "1234.00", "credit", "4417", None),
    # --- HDFC Bank ---
    ("sms", "VM-HDFCBK-S", None, "Sent Rs.85.00\nFrom HDFC Bank A/C *6612\nTo Chai Point\nOn 03/10/26\nRef 627612345673\nNot You?\nCall 18002586161/SMS BLOCK UPI to 7308080808", "transaction", "85.00", "debit", "6612", "chai point"),
    ("sms", "AD-HDFCBK-S", None, "Credit Alert!\nRs.1,200.00 credited to HDFC Bank A/c XX6612 on 02-10-26 from VPA ananya.s@oksbi (UPI 627512345674)", "transaction", "1200.00", "credit", "6612", "ananya"),
    ("sms", "VM-HDFCBK-S", None, "Rs.4,999.00 spent on HDFC Bank Card x3344 at RELIANCE DIGITAL on 2026-10-01:19:22:05. Not You? Call 18002586161", "transaction", "4999.00", "debit", "3344", "reliance digital"),
    ("sms", "VM-HDFCBK-S", None, "UPDATE: INR 15,000.00 debited from A/c XX6612 on 30-SEP-26 for Ach D- BAJAJ FINANCE LTD-5551234. Avl Bal: INR 22,500.00", "transaction", "15000.00", "debit", "6612", "bajaj finance"),
    ("sms", "VM-HDFCBK-S", None, "Update! INR 71,450.00 deposited in HDFC Bank A/c XX6612 on 30-SEP-26 for NEFT Cr-CITI0000004-NOVA LABS PRIVATE LIMITED-SAL SEP 26-CITIN26123456. Avl bal INR 93,950.00. Cheque deposits in A/C are subject to clearing", "transaction", "71450.00", "credit", "6612", "nova labs"),
    ("sms", "VM-HDFCBK-S", None, "Payment of Rs.12,345.00 has been credited to your HDFC Bank Credit Card XX3344 on 29-09-2026. Thank you.", "transaction", "12345.00", "credit", "3344", None),
    ("sms", "VM-HDFCBK-S", None, "HDFC Bank Credit Card XX3344 statement is generated. Total due: Rs.18,250.00, Minimum due: Rs.920.00. Due by 18-10-2026.", "statement", "18250.00", None, "3344", None),
    ("sms", "VM-HDFCBK-S", None, "Money Transferred - Rs 9,000.00 from HDFC Bank A/c **6612 to A/c **2201 on 02-10-26. Ref no 627512345701. Not you? Call 18002586161", "transaction", "9000.00", "debit", "6612", None),
    ("sms", "VM-HDFCBK-S", None, "UPDATE: INR 5,000.00 debited from A/c XX6612 on 05-OCT-26 for Ach D- ICCL- MUTUAL FUND-2601234567. Avl Bal: INR 17,450.00", "transaction", "5000.00", "debit", "6612", "iccl"),
    ("sms", "VM-HDFCBK-S", None, "UPDATE: INR 1,568.00 debited from A/c XX6612 on 02-OCT-26 for SI-STAR HEALTH INSURANCE-POLICY 77889. Avl Bal: INR 16,194.50", "transaction", "1568.00", "debit", "6612", "star health"),
    ("sms", "VM-HDFCBK-S", None, "INR 312.50 credited to A/c XX6612 on 01-OCT-26 towards Dividend from INFOSYS LTD. Avl bal INR 17,762.50", "transaction", "312.50", "credit", "6612", "infosys"),
    ("sms", "VM-HDFCBK-S", None, "Refund of Rs.1,099.00 from AJIO has been credited to your HDFC Bank A/c XX6612 on 03-10-26.", "refund", "1099.00", "credit", "6612", "ajio"),
    ("sms", "AD-HDFCBK-S", None, "Rs.560.00 reversed to your HDFC Bank A/c XX6612 on 02-10-26 against UPI Ref 627512345700.", "failed_or_reversed", None, None, None, None),
    ("sms", "VM-HDFCBK-S", None, "Available Bal in HDFC Bank A/c XX6612 as on 03-OCT-26 is INR 17,450.00. Cheque deposits subject to clearing.", "balance", None, None, None, None),
    # --- ICICI Bank ---
    ("sms", "JD-ICICIB-S", None, "ICICI Bank Acct XX219 debited for Rs 260.00 on 03-Oct-26; UBER INDIA SYSTEMS credited. UPI:627612345675. Call 18002662 for dispute. SMS BLOCK 219 to 9215676766.", "transaction", "260.00", "debit", "219", "uber"),
    ("sms", "JD-ICICIB-S", None, "Dear Customer, Acct XX219 is credited with Rs 3,000.00 on 02-Oct-26 from VIKRAM N. UPI:627512345676-ICICI Bank.", "transaction", "3000.00", "credit", "219", "vikram"),
    ("sms", "JD-ICICIT-S", None, "INR 899.00 spent using ICICI Bank Card XX5521 on 01-Oct-26 on SWIGGY. Avl Limit: INR 61,101.00. If not you, call 1800 2662/SMS BLOCK 5521 to 9215676766", "transaction", "899.00", "debit", "5521", "swiggy"),
    ("sms", "JD-ICICIB-S", None, "ICICI Bank Account XX219 credited:Rs. 54,800.00 on 30-Sep-26. Info NEFT-UTIBN62026093012-ORBIT DATA SERVICES-SALARY. Available Balance is Rs. 61,240.12.", "transaction", "54800.00", "credit", "219", "orbit"),
    ("sms", "JD-ICICIB-S", None, "Your account XX219 has been debited with INR 199.00 on 01-Oct-26 for the AutoPay of SPOTIFY INDIA. UPI Ref No. 627412345677.", "transaction", "199.00", "debit", "219", "spotify"),
    ("sms", "VM-ICICIB-S", None, "INR 2,000.00 withdrawn from ICICI Bank Acct XX219 at ATM on 03-Oct-26 11:42. Avl Bal INR 59,240.12. Not you? Call 18002662.", "transaction", "2000.00", "debit", "219", None),
    ("sms", "JD-ICICIT-S", None, "Dear Customer, refund of INR 799.00 from MYNTRA has been credited to your ICICI Bank Credit Card XX5521 on 02-Oct-26.", "refund", "799.00", "credit", "5521", "myntra"),
    ("sms", "VM-ICICIT-S", None, "ICICI Bank Credit Card XX5521 Statement: Total Amount Due INR 23,450.75; Minimum Amount Due INR 1,175.00; Payment Due Date 20-OCT-26.", "statement", "23450.75", None, "5521", None),
    # --- Axis Bank ---
    ("sms", "VK-AXISBK-S", None, "INR 640.00 debited\nA/c no. XX7710\n03-10-26, 20:14:33\nUPI/P2A/627612345678/MEENA K\nNot you? SMS BLOCKUPI Cust ID to 919951860002\nAxis Bank", "transaction", "640.00", "debit", "7710", "meena"),
    ("sms", "VK-AXISBK-S", None, "Spent\nCard no. XX4410\nINR 2,315\n02-10-26 13:05:41\nBLINKIT\nAvl Lmt INR 48,685\nSMS BLOCK 4410 to 919951860002, if not you - Axis Bank", "transaction", "2315.00", "debit", "4410", "blinkit"),
    ("sms", "VK-AXISBK-S", None, "INR 25,000.00 credited\nA/c no. XX7710\n01-10-26, 10:01:12 IST\nNEFT/AXISN26274012345/SPARKLE MEDIA LLP\nAxis Bank", "transaction", "25000.00", "credit", "7710", "sparkle media"),
    ("sms", "VK-AXISBK-S", None, "INR 432.00 credited to A/c no. XX7710 on 02-10-26 16:20:11 towards refund of UPI/627512345699. Avl Bal INR 20,110.00 - Axis Bank", "refund", "432.00", "credit", "7710", None),
    # --- Kotak ---
    ("sms", "BZ-KOTAKB-S", None, "Sent Rs.349.00 from Kotak Bank AC X8812 to netflixupi.payu@hdfcbank on 03-10-26.UPI Ref 627612345679. Not you, https://kotak.com/KBANKT/Fraud", "transaction", "349.00", "debit", "8812", "netflix"),
    ("sms", "BZ-KOTAKB-S", None, "Received Rs.780.00 in your Kotak Bank AC X8812 from harish.p@okicici on 02-10-26.UPI Ref:627512345680.", "transaction", "780.00", "credit", "8812", "harish"),
    ("sms", "JD-KOTAKB-S", None, "Received Rs.25,000.00 in your Kotak Bank AC X8812 from NEFT-HDFC MF REDEMPTION on 03-10-26.Ref:N627612345702.", "transaction", "25000.00", "credit", "8812", "hdfc mf"),
    # --- Canara Bank ---
    ("sms", "AX-CANBNK-S", None, "An amount of INR 432.00 has been DEBITED to your account XXX554 on 03/10/2026 towards UPI/627612345681/SWIGGY LIMITED. Total Avail.bal INR 12,004.00. - Canara Bank", "transaction", "432.00", "debit", "554", "swiggy"),
    ("sms", "AX-CANBNK-S", None, "An amount of INR 10,000.00 has been CREDITED to your account XXX554 on 01/10/2026 towards NEFT/CNRBN26274555/SELF. Total Avail.bal INR 22,436.00. - Canara Bank", "transaction", "10000.00", "credit", "554", None),
    ("sms", "AX-CANBNK-S", None, "Rs.150.00 paid thru A/C XX0554 on 02-10-26 08:44:12 to ANNAPOORNA MESS, UPI Ref 627512345682. If not done, SMS BLOCKUPI to 9901771222.-Canara Bank", "transaction", "150.00", "debit", "0554", "annapoorna"),
    ("sms", "VM-CANBNK-S", None, "Your account XXX554 is credited by Rs. 5,000.00 on 03-10-26 by Cash Deposit at branch 1234. Total Avail. Bal Rs.27,436.00 - Canara Bank", "transaction", "5000.00", "credit", "554", None),
    # --- Indian Bank, IOB ---
    ("sms", "VM-INDBNK-S", None, "A/c *7761 debited Rs. 520.00 on 03-10-26 to ZOMATO LTD. UPI:627612345683. Not you? SMS BLOCK to 9444394443 -Indian Bank", "transaction", "520.00", "debit", "7761", "zomato"),
    ("sms", "VM-INDBNK-S", None, "Your a/c no. XXXXXX7761 is credited by Rs.2,000.00 on 02-10-2026 by a/c linked to VPA gokul.r@okaxis (UPI Ref no 627512345684).-Indian Bank", "transaction", "2000.00", "credit", "7761", "gokul"),
    ("sms", "VM-IOBCHN-S", None, "Your a/c no. XXXXX3392 is debited for Rs.300.00 on 03-10-2026 and credited to a/c no. XXXXXX1129 (UPI Ref no 627612345685) -IOB", "transaction", "300.00", "debit", "3392", None),
    ("sms", "VM-IOBCHN-S", None, "Your a/c no. XXXXX3392 is credited for Rs.4,500.00 on 01-10-2026 and debited from a/c no. XXXXXX8812 (UPI Ref no 627412345686) -IOB", "transaction", "4500.00", "credit", "3392", None),
    # --- Bank of Baroda, PNB, Union Bank ---
    ("sms", "JM-BOBTXN-S", None, "Rs.230.00 transferred from A/c ...2201 to:UPI/627612345687. Total Bal:Rs.9,870.00CR. Avlbl Amt:Rs.9,870.00(03-10-2026 19:12:44) - Bank of Baroda", "transaction", "230.00", "debit", "2201", None),
    ("sms", "JM-BOBTXN-S", None, "Rs.1500 Credited to A/c ...2201 thru UPI/627512345688 by nithya.m@okhdfcbank. Total Bal:Rs.10,100.00CR. Avlbl Amt:Rs.10,100.00(02-10-2026 09:05:31) - Bank of Baroda", "transaction", "1500.00", "credit", "2201", "nithya"),
    ("sms", "AD-PNBSMS-S", None, "Your A/c XX5590 has been debited for INR 1,099.00 on 03-10-2026 19:40:12 through UPI to AJIO. Avl Bal INR 14,221.30 -PNB", "transaction", "1099.00", "debit", "5590", "ajio"),
    ("sms", "AD-PNBSMS-S", None, "A/c XX5590 credited with INR 30,000.00 on 30-09-2026 10:12:33 by NEFT from TALENTWORKS INDIA. Aval Bal INR 45,320.30 -PNB", "transaction", "30000.00", "credit", "5590", "talentworks"),
    ("sms", "AX-UNIONB-S", None, "A/c *8873 Debited for Rs:89.00 on 03-10-2026 12:01:55 by UPI ref no 627612345689 Avl Bal Rs:6,110.25.If not you, Call 1800222243 -Union Bank of India", "transaction", "89.00", "debit", "8873", None),
    ("sms", "AX-UNIONB-S", None, "A/c *8873 Credited for Rs:5,000.00 on 01-10-2026 17:22:10 by Mob Bk ref no 627412345690 Avl Bal Rs:11,110.25 -Union Bank of India", "transaction", "5000.00", "credit", "8873", None),
    # --- IDFC FIRST, YES, IndusInd, Federal, AU ---
    ("sms", "BZ-IDFCFB-S", None, "Your A/C XXXXXXX9045 has been debited with INR 2,600.00 on 03-OCT-2026 towards UPI/627612345691/AIRTEL PAYMENTS BANK. Avl Bal INR 18,900.00 - IDFC FIRST Bank", "transaction", "2600.00", "debit", "9045", "airtel"),
    ("sms", "BZ-IDFCFB-S", None, "Your A/C XXXXXXX9045 has been credited with INR 7,000.00 on 02-OCT-2026 from IMPS/627512345692/DEEPAK S. Avl Bal INR 21,500.00 - IDFC FIRST Bank", "transaction", "7000.00", "credit", "9045", "deepak"),
    ("sms", "VK-YESBNK-S", None, "INR 450.00 debited from A/c XX3329 on 03-10-2026 14:22 for UPI-627612345693-ZEPTO MARKETPLACE. Avl Bal INR 9,050.00 - YES BANK", "transaction", "450.00", "debit", "3329", "zepto"),
    ("sms", "BZ-INDUSB-S", None, "Your A/C 2XXXXX1188 is debited by INR 1,250.00 towards UPI/627612345694/DMART. Avl Bal INR 15,700.00 - IndusInd Bank", "transaction", "1250.00", "debit", "1188", "dmart"),
    ("sms", "VM-FEDBNK-S", None, "Rs 75.00 debited from your A/c XX4410 using UPI on 03-10-2026 18:21:00 to VPA paytmqr28100505010112abc@paytm - (UPI Ref No 627612345695)-Federal Bank", "transaction", "75.00", "debit", "4410", None),
    ("sms", "VM-AUBANK-S", None, "Debited INR 999.00 from A/c XX6631 on 03-10-26 to MYNTRA DESIGNS UPI Ref 627612345696. Bal INR 31,001.00 - AU Bank", "transaction", "999.00", "debit", "6631", "myntra"),
    # --- cards, payments banks, wallets ---
    ("sms", "AD-AMEXIN-S", None, "Alert: You've spent INR 3,450.00 on your AmEx card ** 41007 at MAKEMYTRIP on 2 October 2026 at 08:41 PM IST. Call 18004190691 if this was not made by you.", "transaction", "3450.00", "debit", "41007", "makemytrip"),
    ("sms", "VM-ONECRD-S", None, "Rs. 1,240.00 spent at AMAZON on your OneCard ending 7729 on 02/10/2026. Available limit: Rs. 58,760.00. Not you? Report at onecard app", "transaction", "1240.00", "debit", "7729", "amazon"),
    ("sms", "VM-SBICRD-S", None, "We have received payment of Rs.8,910.00 towards your SBI Card ending 9921 on 03/10/2026. Thank you.", "transaction", "8910.00", "credit", "9921", None),
    ("sms", "VM-SBICRD-S", None, "Statement for SBI Card ending 9921: Total Due Rs.8,910.00, Min Due Rs.450.00, Due Date 22 Oct 2026.", "statement", "8910.00", None, "9921", None),
    ("sms", "VM-PAYTMB-S", None, "Rs 60 paid to Rameshwaram Cafe from Paytm Payments Bank a/c XX7712. UPI Ref: 627612345697. Balance: Rs 1,230", "transaction", "60.00", "debit", "7712", "rameshwaram"),
    ("sms", "VM-AIRBNK-S", None, "Rs.300 debited from your Airtel Payments Bank a/c XX0091 for payment to IRCTC on 03-10-2026. Txn ID 627612345698. Bal Rs.1,520", "transaction", "300.00", "debit", "0091", "irctc"),
    ("sms", "VM-IHMCLF-S", None, "Rs.85.00 deducted from your FASTag wallet for vehicle TN09AB1234 at Paranur Toll Plaza on 03-10-2026 09:12:44. Avl Bal Rs.415.00", "transaction", "85.00", "debit", None, "paranur"),
    ("sms", "VM-BAJAJF-S", None, "Dear Customer, your EMI of Rs.3,250.00 for loan A/c 4040CD12345678 has been debited on 05-10-2026. Thank you - Bajaj Finance", "transaction", "3250.00", "debit", None, None),
    # --- bills ---
    ("sms", "VM-TNPDCL-S", None, "TNPDCL: Bill amount Rs.1,240.00 for service no 06-123-456-789 is due on 15-10-2026. Pay online at tnebnet.org to avoid disconnection.", "bill_due", "1240.00", None, None, None),
    ("sms", "VM-AIRTEL-S", None, "Your Airtel Postpaid bill of Rs.749.00 for 98XXXXXX45 is due on 20-Oct-2026. Pay now via Airtel Thanks app: i.airtel.in/pay", "bill_due", "749.00", None, None, None),
    ("sms", "JM-ACTFBR-S", None, "Dear Customer, your ACT Fibernet bill of Rs.1,179 for Account 104422331 is due on 12/10/2026. Pay via ACT app.", "bill_due", "1179.00", None, None, None),
    ("sms", "VM-BSNLIN-S", None, "BSNL: Your landline/FTTH bill for A/c 9012345678 of Rs 699 is due on 18-10-2026.", "bill_due", "699.00", None, None, None),
    # --- failures and reversals ---
    ("sms", "VM-SBIUPI-S", None, "Dear UPI user, your transaction of Rs.250.00 to SWIGGY has failed. Amount if debited will be reversed in 48 hrs. -SBI", "failed_or_reversed", None, None, None, None),
    ("sms", "BZ-KOTAKB-S", None, "Your UPI transaction of Rs 1,200.00 to IRCTC could not be completed. Any amount debited will be refunded within 3 working days.", "failed_or_reversed", None, None, None, None),
    # --- balances ---
    ("sms", "VM-SBIINB-S", None, "Dear Customer, Available Balance in A/c XXXXX4417 is Rs.80,200.40 as on 03/10/2026 10:00:00. -SBI", "balance", None, None, None, None),
    # --- OTPs (never stored) ---
    ("sms", "VM-HDFCBK-T", None, "OTP is 448812 for txn of INR 2,345.00 at AMAZON on HDFC Bank card ending 3344. Valid till 10:21. Do not share OTP for security reasons.", "otp", None, None, None, None),
    ("sms", "JD-ICICIB-T", None, "Dear Customer, 731244 is OTP for INR 5,999.00 txn on ICICI Bank Card XX5521 at FLIPKART. OTP valid for 10 mins. Do not share with anyone.", "otp", None, None, None, None),
    ("sms", "VM-SBIOTP-T", None, "OTP for online purchase of Rs. 1,799.00 at NYKAA thru State Bank Debit Card ending 1234 is 552211. Do not share this with anyone.", "otp", None, None, None, None),
    ("sms", "BZ-PHONPE-T", None, "<#> 552198 is your PhonePe verification code. Do not share it with anyone. kQ3/xvH2Gd", "otp", None, None, None, None),
    ("sms", "VM-KOTAKB-T", None, "Your OTP to authorise the UPI transaction of Rs 4,000.00 to rahul.k@okhdfcbank is 129334. Kotak never asks for OTP.", "otp", None, None, None, None),
    # --- promotions and other notices (never become transactions) ---
    ("sms", "VM-HDFCBK-S", None, "Pre-approved Personal Loan of up to Rs.8,00,000 ready for you in 10 seconds! T&C. Apply: hdfcbk.io/pl", "promo", None, None, None, None),
    ("sms", "AD-AXISBK-S", None, "Get 10% instant discount up to Rs.1,500 on Flipkart with Axis Bank Credit Cards. Sale ends Sunday. T&C apply", "promo", None, None, None, None),
    ("sms", "VM-JIOINF-S", None, "Unlimited 5G + 2GB/day for 84 days at Rs.859! Recharge now on MyJio.", "promo", None, None, None, None),
    ("sms", "JD-SWIGGY-S", None, "Craving biryani? Get 50% OFF up to Rs.100 on your next order. Use code BIRYANI50. Order now!", "promo", None, None, None, None),
    ("sms", "VM-HDFCBK-S", None, "Dear Customer, your HDFC Bank Debit Card XX1122 has been dispatched via Blue Dart AWB 12345678. -HDFC Bank", "other", None, None, None, None),
    ("sms", "JD-ICICIB-S", None, "Your ICICI Bank iMobile Pay login was successful on 03-10-2026 10:22 from a new device.", "other", None, None, None, None),
    ("sms", "VM-AMAZON-S", None, "Your Amazon order of 'Boat Rockerz 450' has been delivered. Rate your experience: amzn.in/r", "other", None, None, None, None),
    ("sms", "VM-SBIINB-S", None, "Your nominee details for A/c XXXXX4417 have been updated successfully. -SBI", "other", None, None, None, None),
    # --- emails ---
    ("email", "HDFC Bank InstaAlerts <alerts@hdfcbank.bank.in>", "View: Account update for your HDFC Bank A/c",
     "Dear Customer, Rs.2,450.00 has been debited from account **6612 to VPA zomato@hdfcbank ZOMATO on 03-10-26. Your UPI transaction reference number is 627612345703.", "transaction", "2450.00", "debit", "6612", "zomato"),
    ("email", "ICICI Bank <credit_cards@icicibank.com>", "Transaction alert for your ICICI Bank Credit Card",
     "Dear Customer, your ICICI Bank Credit Card XX5521 has been used for a transaction of INR 2,249.00 on Oct 03, 2026 at 18:45:10. Info: AMAZON PAY INDIA.", "transaction", "2249.00", "debit", "5521", "amazon"),
    ("email", "Uber Receipts <noreply@uber.com>", "Your Thursday evening trip with Uber", "Thanks for riding, Priya\nTotal ₹ 312.45\nTrip fare ₹ 287.00\nBooking fee ₹ 25.45", "order_receipt", "312.45", None, None, None),
    ("email", "Zomato <noreply@zomato.com>", "Your Zomato order from Meghana Foods", "Order ID: 6123456789\nMeghana Special Biryani x 1 ₹350\nTotal paid ₹412.50", "order_receipt", "412.50", None, None, None),
    ("email", "Amazon.in <auto-confirm@amazon.in>", "Your Amazon.in order of \"boAt Airdopes 141...\"", "Order #408-1234567-7654321\nOrder Total: ₹1,299.00\nArriving Monday", "order_receipt", "1299.00", None, None, None),
    ("email", "Google Play <googleplay-noreply@google.com>", "Your Google Play Order Receipt from Oct 3, 2026", "Thank you. Your order GPA.3312-4455-6677-88990 is complete.\nYouTube Premium (Monthly)\nTotal: ₹149.00/month", "order_receipt", "149.00", None, None, None),
]


def messages() -> list[RawMessage]:
    out = []
    for i, (channel, sender, subject, body, kind, amount, direction, mask, payee) in enumerate(CASES):
        expect = {k: v for k, v in (("amount", amount), ("direction", direction), ("mask", mask), ("payee", payee)) if v}
        out.append(RawMessage(channel=channel, sender=sender, received_at=T, subject=subject, body=body,
                              html=f"<html><body><p>{body}</p></body></html>" if channel == "email" else None,
                              truth={"kind": kind, "template": f"real_{i}", "txn_id": None, "expect": expect}))
    return out
