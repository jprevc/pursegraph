"""PROTOTYPE — throwaway. Step 1 of the #6 Category-suggestion benchmark.

Pulls every Transaction out of the sample Statements (the #5 hand parsers, extended to keep
the extra text a real parser would put in `raw`: Sparkasse's purpose line, N26's own category
line, Revolut's "To:" merchant line) and writes them to samples/PROTOTYPE_transactions.json.

Run:  .venv/bin/python prototypes/categorize/extract.py
Everything it writes stays in the gitignored samples/ directory.
"""
import json, re
from datetime import datetime
from decimal import Decimal

import pdfplumber

SAMPLES = {
    "sparkasse": "samples/document(9).pdf",
    "revolut": "samples/account-statement_2026-05-01_2026-10-12_en-us_7a3afe.pdf",  # superset of the Sept one
    "n26": "samples/statement-2026-05.pdf",  # the Sept N26 Statement has no rows
}
OUT = "samples/PROTOTYPE_transactions.json"
IBAN = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{11,30})\b")
DATED = re.compile(r"^\d\d\.\d\d\.\d{4}( |$)")


def text_of(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def eu(s):
    return Decimal(s.replace(".", "").replace(",", "."))


def us(s):
    return Decimal(s.replace("€", "").replace(",", ""))


def sparkasse(t):
    lines = t.splitlines()
    row = re.compile(r"^(\d\d\.\d\d\.\d{4}) ?(.*?) ?(\d{1,3}(?:\.\d{3})*,\d\d)(?: (\S.*))?$")
    out, sign = [], None
    for i, l in enumerate(lines):
        if l.startswith("PRILIVI"): sign = 1
        elif l.startswith("ODLIVI"): sign = -1
        elif l.startswith("Končno stanje"): break
        elif sign and (m := row.match(l)):
            d, name, amt, _ref = m.groups()
            iban, extra = None, []
            for j in range(i + 1, min(i + 6, len(lines))):
                if DATED.match(lines[j]):
                    rest = lines[j][11:]
                    if m2 := IBAN.search(rest):
                        iban = m2.group(1)
                        rest = rest.replace(iban, "")
                    extra.append(rest.strip())  # "Namen plačila" (purpose)
                    break
                if re.search(r"skupaj|\bod \d", lines[j]):
                    break
                extra.append(lines[j].strip())  # wrapped name / purpose lines
            extra = [e for e in extra if e and not re.fullmatch(r"\d{1,4}", e)]
            if not name.strip() and extra:  # e.g. interest: the name is on the value-date line
                name = extra.pop()
            out.append(dict(date=datetime.strptime(d, "%d.%m.%Y").date().isoformat(),
                            amount=sign * eu(amt), description=name.strip(),
                            detail=" / ".join(extra), iban=iban))
    return out


def revolut(t):
    m = re.search(r"Account \(Current Account\) (€[\d,.]+)", t)
    prev = us(m.group(1))
    lines = t.splitlines()
    row = re.compile(r"^([A-Z][a-z]{2} \d{1,2}, \d{4}) (.*) (€[\d,]+\.\d\d) (€[\d,]+\.\d\d)$")
    out = []
    for i, l in enumerate(lines):
        if m := row.match(l):
            d, desc, amt, bal = m.groups()
            amt, bal = us(amt), us(bal)
            signed = amt if bal - prev == amt else -amt
            prev = bal
            iban, detail = None, ""
            for nxt in lines[i + 1:i + 4]:
                if row.match(nxt): break
                if nxt.startswith(("From:", "To:")):
                    detail = nxt.split(":", 1)[1].strip()
                    if m2 := IBAN.search(nxt): iban = m2.group(1)
                elif nxt.startswith("Reference:"):
                    detail = (detail + " / " + nxt).strip(" /")
            out.append(dict(date=datetime.strptime(d, "%b %d, %Y").date().isoformat(),
                            amount=signed, description=desc, detail=detail, iban=iban))
    return out


def n26(t):
    lines = t.splitlines()
    row = re.compile(r"^(.+?) (\d\d\.\d\d\.\d{4}) ([+-]?[\d.]+,\d\d)€$")
    out = []
    for i, l in enumerate(lines):
        if m := row.match(l):
            desc, d, amt = m.groups()
            iban, detail = None, lines[i + 1].strip()  # "Mastercard • Car" / "Card Reorder Fee"
            for nxt in lines[i + 1:i + 4]:
                if nxt.startswith("IBAN:") and (m2 := IBAN.search(nxt)): iban = m2.group(1)
            out.append(dict(date=datetime.strptime(d, "%d.%m.%Y").date().isoformat(),
                            amount=eu(amt), description=desc, detail=detail, iban=iban))
    return out


def main():
    rows = []
    for bank, fn in (("sparkasse", sparkasse), ("revolut", revolut), ("n26", n26)):
        for x in fn(text_of(SAMPLES[bank])):
            rows.append({"id": f"{bank}-{len(rows):03}", "bank": bank, **x, "amount": str(x["amount"])})
    json.dump(rows, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"wrote {len(rows)} Transactions to {OUT}")


if __name__ == "__main__":
    main()
