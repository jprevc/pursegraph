# Statement export formats: Sparkasse SI, OTP banka, N26, Revolut

Research for [#2](https://github.com/jprevc/pursegraph/issues/2) (part of #1). Researched 2026-10-12.

**Legend.** **V** = verified against a primary source (bank help page or manual, or a real export
fixture committed to a public parser's test suite). **I** = inferred (secondary source, a parser
author's comment, or reasoning from related products). **?** = unknown; needs a real sample.

## TL;DR

| | Sparkasse SI (retail) | OTP banka SI (retail) | N26 | Revolut (personal) |
|---|---|---|---|---|
| Statement PDF | Yes, monthly, in Net.Stik (V) | Yes, in Bank@Net / mBank@Net (V) | Yes, monthly "Balance statement" (app + web) (V) | Yes, any month range, per currency (app + web) (V) |
| CSV | None documented for retail (?) | "Export" button per statement, format undocumented (?) | Yes, "Account activity report", **web only**, custom range (V) | "Excel" option, which is actually a CSV (I, strong) |
| camt.053 / XML | Business only: daily statements as "XML SEPA" + PDF (V); retail ? | Business: daily statements "XML in pdf" (V); retail ? | No | Business only: CSV, camt.053, MT940 (I, from help-centre snippets); personal: no |
| Delimiter / encoding | ? | ? | `,` / UTF-8 (V from fixtures) | `,` / UTF-8 (V from fixtures) |
| Dates | ? (Slovenian `dd.mm.yyyy` likely) | ? (same) | `YYYY-MM-DD` (V); a `DD.MM.YYYY` variant also handled by parsers (I) | `YYYY-MM-DD HH:MM:SS` (V) |
| Decimal | ? (decimal comma likely in PDF) | ? | dot (V) | dot (V) |
| Debit sign | ? | ? | negative (V) | negative; fee in separate positive `Fee` column (V) |
| Opening/closing balance | PDF: very likely (statutory "izpisek stanja in prometa") (I) | PDF: likely (I) | CSV: **no** (V); PDF: likely (I) | CSV: running `Balance` per row (V); PDF: "balance summary" (V) |
| Counterparty IBAN + name | PDF/XML: likely (I) | PDF/XML: likely (I) | CSV: `Partner Name`, `Partner Iban` (V) | CSV: **no IBAN**; only free-text `Description` (V) |
| Bank transaction ID | camt.053 has one (I) | camt.053 has one (I) | CSV: **no** (V) | CSV: **no** (V) |
| PDF text layer | ? | ? | likely yes (I) | likely yes (I) |

The design takeaways for Pursegraph are at the end.

## N26

### What is offered (V)

From N26's own support page ([How to get a bank statement](https://support.n26.com/en-eu/fixing-an-issue/payments-and-transfers/how-to-export-a-list-of-my-transactions);
same text on [en-de](https://support.n26.com/en-de/account-and-personal-details/bank-statements-and-confirmations/how-to-get-bank-statement-n26)):

- **Balance statements**: one calendar month, **PDF only**. In the app: Finances, pick the account or
  Space, gear icon, "Balance statements". On web: Home, account or Space, "Downloads", "Bank statements".
- **Account activity reports**: custom date range, **PDF or CSV**, **web only**.
- Statements contain "your total balance and every transaction", plus full name, IBAN and BIC. They
  are "official documents ... fully valid without a signature or stamp".
- Spaces (sub-accounts) have their own statements, and their CSV is also web-only.
- N26 offers no camt.053, MT940 or OFX export to retail customers (nothing in their help centre).

### CSV format

The current header (post-2023), verified from real export fixtures in
[drola/bank-statements-import `fixtures/test_n26.csv`](https://github.com/drola/bank-statements-import/blob/main/fixtures/test_n26.csv)
and the header table in [siddhantgoel/beancount-n26](https://github.com/siddhantgoel/beancount-n26/blob/main/beancount_n26/__init__.py):

```
"Booking Date","Value Date","Partner Name","Partner Iban",Type,"Payment Reference","Account Name","Amount (EUR)","Original Amount","Original Currency","Exchange Rate"
"2022-10-04","2022-10-04","Johnny","IT1234567890","MoneyBeam","The gift","","-20.0","","",""
"2022-12-01","2022-12-01","DIGITALOCEAN.COM","","MasterCard Payment","-","","-1.61","-1.66","USD","0.9698795181"
```

| Property | Value | Status |
|---|---|---|
| Delimiter / quoting | `,`; fields quoted, but quoting is inconsistent (the bare `Type` column) | V |
| Encoding | UTF-8 | V (fixtures, parsers default to it) |
| Date | ISO `YYYY-MM-DD`, both booking and value date | V. [you-need-a-parser](https://github.com/leolabs/you-need-a-parser/blob/master/packages/ynap-parsers/src/de/n26/n26.ts) also accepts `DD.MM.YYYY`, which suggests some exports use it (I) |
| Number | dot decimal, no thousands separator, varying precision (`-20.0`, `-5.99`) | V |
| Sign | negative = money out | V |
| Currency | always EUR in `Amount (EUR)`; card FX in `Original Amount` / `Original Currency` / `Exchange Rate` | V |
| Counterparty | `Partner Name`, `Partner Iban` (empty for card payments) | V |
| Reference | `Payment Reference` (`-` when empty) is the remittance text, not a bank ID | V |
| Transaction ID | **none** | V |
| Balances | **none** (no opening, closing or running balance) | V |
| `Account Name` | names the Space (sub-account) | I |
| `Type` values | e.g. `MasterCard Payment`, `MoneyBeam`, `Income`, `Presentment`, `Debit Transfer` | V (fixtures) |

**Header variants.** The pre-2023 "legacy" header was
`"Date","Payee","Account number","Transaction type","Payment reference","Amount (EUR)","Amount (Foreign Currency)","Type Foreign Currency","Exchange Rate"`
([fixture](https://github.com/drola/bank-statements-import/blob/main/fixtures/test_n26_legacy.csv)).
The headers are also **localised by app language**. beancount-n26 ships German
(`Datum, Empfänger, Kontonummer, Transaktionstyp, Verwendungszweck, …, Betrag (EUR), …`) and French
variants, and has an optional `Category` column (V, source code). A parser must match columns by name
and accept several header dialects.

### PDF

- Balance statements are generated documents, not scans, so a text layer is very likely (I).
- A public sample of an N26 statement layout (Sept 2024, on Scribd) shows per entry: description,
  booking date, amount, then IBAN and value date on the next line (I, secondary). Multi-line entries
  mean PDF parsing will need layout-aware logic.
- Opening/closing ("previous/new") balance on the PDF is likely but **not verified**.

## Revolut (personal)

### What is offered

- **Account statement per currency** (V, help.revolut.com "Download an account statement for a
  specific currency", quoted via search snippets because the page sits behind a bot check):
  Home, Accounts, pick the currency, More, Statement, choose timeframe and **document type (PDF or
  Excel)**, Generate. Statements contain the account holder's name and address, local and
  international IBAN/BIC, a **balance summary**, **pending, completed and reverted transactions**,
  and Personal/Group Pocket transactions. One statement per currency account.
- The **web app** (app.revolut.com) has the same "Statement" button with the "Excel" option. That
  option **downloads a CSV**, not .xlsx (I, strong: [lastunicorn/revolut-toolkit README](https://github.com/lastunicorn/revolut-toolkit)).
- Community reports say some app versions only offer PDF, and that Excel was removed on Android at
  some point (I, [community.revolut.com/t/data-export](https://community.revolut.com/t/data-export/76631)).
  **Use the web app for CSV.**
- Per-transaction PDF confirmations exist, but they don't help with bulk import.
- **Revolut Business** offers PDF, CSV, XML (camt.053) and TXT (MT940) (I, help-centre snippets).
  None of these are documented for personal accounts.

### CSV format (V, real export fixture)

From [akashastrub/expensifyR `data/revolut_eur_demo.csv`](https://github.com/akashastrub/expensifyR/blob/main/data/revolut_eur_demo.csv),
matching the column list in the [ofxstatement-revolut](https://github.com/mlaitinen/ofxstatement-revolut/blob/master/src/ofxstatement/plugins/revolut.py) source:

```
Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance
TRANSFER,Current,2022-07-01 10:23:25,2022-07-01 10:23:29,Rent,-600.00,0.00,EUR,COMPLETED,1551.96
CARD_PAYMENT,Current,2022-07-01 09:50:31,2022-07-02 14:45:25,Mcdonalds,-8.19,0.00,EUR,COMPLETED,1543.77
```

| Property | Value | Status |
|---|---|---|
| Delimiter / quoting | `,`, unquoted unless needed | V |
| Encoding | UTF-8 | I (parsers assume it; BOM unknown) |
| Date | `YYYY-MM-DD HH:MM:SS`, two columns: `Started Date` (initiated) and `Completed Date` (settled, can be days later) | V (ofxstatement uses `%Y-%m-%d %H:%M:%S`) |
| Timezone | not stated; personal statements are believed to be UTC | ? |
| Number | dot decimal, 2 dp | V |
| Sign | negative = money out; `Fee` is a separate, positive column that is also debited | V (fee handling: I) |
| `State` | `COMPLETED`, `PENDING`, `REVERTED`, `DECLINED`. Pending rows are later superseded, so import only `COMPLETED` | V (values) / I (supersede behaviour) |
| `Product` | `Current`, `Savings`, `Deposit`, … (Pockets and savings vaults are in the same file) | I |
| `Type` | `CARD_PAYMENT`, `TRANSFER`, `TOPUP`, `EXCHANGE`, `CARD_REFUND`, … | V (subset seen in fixture) |
| Counterparty | **only free-text `Description`** (merchant or "To John Smith"); **no IBAN** | V |
| Transaction ID | **none** | V |
| Balances | **running `Balance` after each row**, so opening = first balance − first amount (+ fee), closing = last balance | V (column); balance can be empty on non-completed rows (I) |
| Currency | one currency per file in practice (statement is per currency account) | I |

An older Revolut CSV dialect, `Completed Date ; Reference ; Paid Out (EUR) ; Paid In (EUR) ; Exchange Out; Exchange In ; Balance (EUR); Exchange Rate ; Category`
(semicolon-separated, with separate in/out columns), shows up in [you-need-a-parser tests](https://github.com/leolabs/you-need-a-parser/blob/master/packages/ynap-parsers/src/international/revolut/revolut.spec.ts).
It is probably obsolete, but old downloaded files may still be around.

### PDF

- Generated document with a "balance summary" (V, help centre). This is presumably the opening
  balance, money in, money out and closing balance per product, but the exact fields are unverified.
- Text layer very likely (I). Several third-party PDF-to-CSV converters exist for Revolut, which
  implies extractable text.

## Sparkasse (Sparkasse d.d., Slovenia)

Retail channels: **Net.Stik** (web) and **M.Stik** (mobile app); a "Moj Sparkasse" portal is
mentioned in the terms effective 30 July 2026. Business channels: **Net.StikPRO** / **Pro.Stik**.

### What is documented

- Retail Net.Stik manual ([navodila-za-uporabo-netstik.pdf](https://cdn.erstegroup.com/content/dam/si/spksi/www_sparkasse_si/dev/sodobne-poti/Dokumentacija/navodila-za-uporabo-netstik.pdf),
  dated 2026-09-30, 19 pp.) (V): menu "Računi" lets you review balances, **"Pregled izpiskov"**
  (statement list for a chosen period), and payment archive. "Sprememba parametrov izpiska" chooses
  delivery **electronically in Net.Stik or on paper**. The manual **mentions no export, CSV, XML or
  file format at all**.
- General terms for the current account ([SPP Transakcijski račun](https://www.sparkasse.si/content/dam/si/spksi/www_sparkasse_si/corpo/ceniki/SPP%20Transakcijski%20ra%C4%8Dun.pdf)) (V):
  the bank sends an "obvestilo-izpisek" at least **monthly** (post, branch pickup, or e-bank) within
  five working days after the period, the "izpisek stanja in prometa". The name ("statement of balance
  and turnover") strongly implies opening and closing balances (I).
- Business FAQ ([Kako lahko dostopam do izpiskov?](https://www.sparkasse.si/sl/gospodarstvo/pogosta-vprasanja/dostop-do-izpiskov)) (V, business):
  monthly statements are in "Produkti > Izpiski in dokumenti" as **PDF**. **Daily statements** (company
  accounts) can be exported per statement via "Akcija" as **"XML SEPA" or PDF**.
- 2024 business migration letter: the new business e-bank supports "uvoz in izvoz dokumentov v različnih
  formatih (csv, xml …)" (I, business only).

### Inference

- The "XML SEPA" statement in Slovenia is almost certainly **camt.053.001.02**. The ZBS
  (Slovenian banking association) SEPA handbook defines camt.052 (promet), **camt.053.001.02
  (izpisek)** and camt.054 as the standard bank-to-customer formats
  ([ZBS priročnik, Jan 2013, via Addiko](https://www.addiko.si/static/uploads/si-sepa-zbs-prirocnik-izmenjava-podatkov-za-kreditna-placila-jan-2013.pdf), V for the standard).
  camt.053 carries opening/closing balances (`OPBD`/`CLBD`), counterparty name and IBAN, a bank
  reference (`AcctSvcrRef`), end-to-end ID and SI/RF creditor references.
- Whether retail Net.Stik exposes that XML (or a CSV of the transaction list) is **unknown**. The
  retail manual's silence suggests retail gets **PDF only**.
- Slovenian conventions make it likely the PDF uses `dd.mm.yyyy` dates and decimal comma with `.`
  thousands separators (I).

## OTP banka (Slovenia; ex-NKBM, which absorbed SKB in 2023)

Retail channels: **Bank@Net** (web) and **mBank@Net** (mobile). Business: **Bank@Net com**,
**mBank@Net com**, **eBank@Net com** (Halcom-based, ex-SKB).

### What is documented

- Retail help ([Bank@Net pomoč – računi](https://www.otpbanka.si/bnk-pomoc-racuni)) (V): "Vsi izpiski
  za vaš transakcijski račun so vam dostopni v zavihku 'Računi' … kliknete na 'Izpiski'." For the
  fastest export, log in to **Bank@Net** (web): "Vsak izpisek bo imel možnost izvoza". The file format
  is shown only in a screenshot and is **not stated in text**.
- Business notice on digital documents ([fileid=320594](https://www.otpbanka.si/downloadfile.ashx?fileid=320594), Aug 2024) (V, business):
  "Dnevni izpiski TRR (EUR): **XML in pdf**"; daily FX statement: XML and PDF; the monthly account
  charge statement is sent as an e-račun (e-SLOG XML).
- Business Bank@Net com manual ([fileid=319844](https://www.otpbanka.si/downloadfile.ashx?fileid=319844), Aug 2024, 70 pp.) (V, business):
  - Accounts list "IZVOZI": you choose the **delimiter** and get a file for MS Excel (a delimited CSV/TXT).
  - "Promet" (transaction list) has filters, comments and complaint actions; no export described there.
  - "Izpiski": select one or several statements, click IZVOZI, then "izberete **vrsto datoteke**" (choose
    the file type), "ki jo nato uvozite v druge programe (npr. računovodske)". The file types are not listed.

### Inference

- Retail Bank@Net and business Bank@Net com look like the same platform (same vendor UI, same "Izpiski"
  + export idiom), so the retail export probably offers **PDF and XML (camt.053.001.02, per the ZBS
  standard)**, possibly CSV too (I, moderate). Not verified.
- Same Slovenian number and date conventions as Sparkasse are likely (I).

## Gaps only a real sample can close

1. **Sparkasse retail**: does Net.Stik or M.Stik offer anything beyond PDF (CSV of "Promet", XML)? Need
   one real PDF to check text layer, column layout, date/number format, opening/closing balance, and
   whether counterparty IBAN, reference (SI00/RF) and a bank transaction ID are printed.
2. **OTP retail**: which file types the per-statement "Izvoz" offers in Bank@Net (screenshot or file).
   If XML: confirm camt.053 version (001.02 vs newer) and which IDs are filled (`AcctSvcrRef`,
   `EndToEndId`). If CSV: delimiter, encoding (UTF-8 vs Windows-1250), decimal comma.
   Also the PDF text layer.
3. **Slovenian banks, statement granularity**: are retail statements monthly or per movement day ("dnevni
   izpisek")? This affects how Statements map to periods and the balance check.
4. **N26**: confirm the header language for our users (EN vs DE) and the date format in a 2026
   export (ISO vs `DD.MM.YYYY`); check whether the PDF shows opening/closing balance and whether its
   text extracts cleanly; whether the CSV includes Spaces in one file or per Space.
5. **Revolut**: whether a Slovenian-language app localises the CSV headers; timezone of timestamps;
   whether a UTF-8 BOM is present; exact PDF balance-summary fields; whether the "Excel" option still
   exists on web and in the iOS/Android app in 2026; how fees on FX and exchanges appear (separate rows
   vs `Fee`).
6. **Duplicate detection**: neither N26 nor Revolut CSVs contain a transaction ID, so deduplication
   must use a content hash (date + amount + counterparty/description + per-day ordinal). Check against
   real overlapping exports that re-exports are byte-stable (Revolut pending to completed changes rows).

## Implications for Pursegraph (for the map, not decisions)

- **Balance check**: possible for Revolut CSV (running balance) and, presumably, all PDFs and camt.053.
  **Not possible from the N26 CSV alone**: it has no balances, so it would need the N26 PDF or a
  user-entered opening balance.
- **Transfer detection by IBAN**: works for N26 (`Partner Iban`) and presumably SI banks
  (PDF/camt.053). **Revolut gives no counterparty IBAN**, only description text such as "To NAME" or
  "Top-up by *1234", so Transfers involving Revolut must be matched by amount + date + name.
- **Parsers must key on column names and tolerate dialects** (N26 has at least 3 header variants;
  Revolut at least 2).
- If either Slovenian bank turns out to offer camt.053 to retail customers, prefer it over PDF: it is
  standardised, carries balances and IDs, and one parser covers both banks.
