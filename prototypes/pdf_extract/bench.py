"""PROTOTYPE — throwaway. Answers: can PDF Statements be parsed reliably, and should
each bank use a hand-written parser or the local LLM (text or vision)?

Run:  .venv/bin/python prototypes/pdf_extract/bench.py [model ...]
Reads real Statements from samples/ (gitignored); prints only aggregate scores.
"""
import base64, collections, csv, io, json, re, sys, time, urllib.request
from datetime import datetime
from decimal import Decimal

import pdfplumber

OLLAMA = "http://192.168.50.188:11434"
SAMPLES = {
    "sparkasse": "samples/document(9).pdf",
    "revolut": "samples/account-statement_2026-09-01_2026-09-30_en-us_a4f3b2.pdf",
    "n26": "samples/statement-2026-05.pdf",
}
REVOLUT_CSV = "samples/account-statement_2026-06-01_2026-10-12_en-us_457150.csv"


def text_of(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def eu(s):  # "1.234,56" -> Decimal
    return Decimal(s.replace(".", "").replace(",", "."))


def us(s):  # "€1,234.56" -> Decimal
    return Decimal(s.replace("€", "").replace(",", ""))


IBAN = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{11,30})\b")

# ---------------------------------------------------------------- hand parsers

def parse_sparkasse(t):
    lines = t.splitlines()
    opening = eu(re.search(r"Začetno stanje ([\d.,]+) EUR", t).group(1))
    closing = eu(re.search(r"Končno stanje ([\d.,]+) EUR", t).group(1))
    row = re.compile(r"^(\d\d\.\d\d\.\d{4}) ?(.*?) ?(\d{1,3}(?:\.\d{3})*,\d\d)(?: (\S.*))?$")
    txns, sign = [], None
    for i, l in enumerate(lines):
        if l.startswith("PRILIVI"): sign = 1
        elif l.startswith("ODLIVI"): sign = -1
        elif l.startswith("Končno stanje"): break
        elif sign and (m := row.match(l)):
            d, name, amt, _ref = m.groups()
            iban = None
            # IBAN sits on the row's second dated line, after any wrapped name lines
            for j in range(i + 1, min(i + 5, len(lines))):
                if re.match(r"\d\d\.\d\d\.\d{4} ", lines[j]):
                    if m2 := IBAN.search(lines[j]):
                        iban = m2.group(1)
                        if j + 1 < len(lines) and re.fullmatch(r"\d{1,4}", lines[j + 1]):
                            iban += lines[j + 1]  # wrapped IBAN tail
                    break
            txns.append(dict(date=datetime.strptime(d, "%d.%m.%Y").date().isoformat(),
                             description=name.strip(), amount=sign * eu(amt), iban=iban))
    return opening, closing, txns


def parse_revolut(t):
    m = re.search(r"Account \(Current Account\) (€[\d,.]+) (€[\d,.]+) (€[\d,.]+) (€[\d,.]+)", t)
    opening, closing = us(m.group(1)), us(m.group(4))
    lines = t.splitlines()
    row = re.compile(r"^([A-Z][a-z]{2} \d{1,2}, \d{4}) (.*) (€[\d,]+\.\d\d) (€[\d,]+\.\d\d)$")
    txns, prev = [], opening
    for i, l in enumerate(lines):
        if m := row.match(l):
            d, desc, amt, bal = m.groups()
            amt, bal = us(amt), us(bal)
            signed = amt if bal - prev == amt else -amt  # sign from balance movement
            prev = bal
            iban = None
            for nxt in lines[i + 1:i + 4]:
                if nxt.startswith(("From:", "To:")) and (m2 := IBAN.search(nxt)):
                    iban = m2.group(1)
            txns.append(dict(date=datetime.strptime(d, "%b %d, %Y").date().isoformat(),
                             description=desc, amount=signed, iban=iban))
    return opening, closing, txns


def parse_n26(t):
    opening = eu(re.search(r"Previous balance ([+-][\d.,]+)€", t).group(1).lstrip("+"))
    closing = eu(re.search(r"Your new balance ([+-][\d.,]+)€", t).group(1).lstrip("+"))
    lines = t.splitlines()
    row = re.compile(r"^(.+?) (\d\d\.\d\d\.\d{4}) ([+-]?[\d.]+,\d\d)€$")
    txns = []
    for i, l in enumerate(lines):
        if m := row.match(l):
            desc, d, amt = m.groups()
            iban = None
            for nxt in lines[i + 1:i + 4]:
                if nxt.startswith("IBAN:") and (m2 := IBAN.search(nxt)):
                    iban = m2.group(1)
            txns.append(dict(date=datetime.strptime(d, "%d.%m.%Y").date().isoformat(),
                             description=desc, amount=eu(amt), iban=iban))
    return opening, closing, txns


HAND = {"sparkasse": parse_sparkasse, "revolut": parse_revolut, "n26": parse_n26}

# ---------------------------------------------------------------- LLM parser

SCHEMA = {
    "type": "object",
    "properties": {
        "opening_balance": {"type": "number"},
        "closing_balance": {"type": "number"},
        "transactions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "booking date, YYYY-MM-DD"},
                "description": {"type": "string"},
                "amount": {"type": "number", "description": "negative = money out, positive = money in"},
                "counterparty_iban": {"type": ["string", "null"]},
            },
            "required": ["date", "description", "amount", "counterparty_iban"],
        }},
    },
    "required": ["opening_balance", "closing_balance", "transactions"],
}

PROMPT = """Extract every account transaction from this bank statement.
Rules:
- Only the EUR account; ignore other currencies, summaries, totals, legal text and page footers.
- One entry per transaction, in statement order. Do not merge or skip any.
- amount: negative for money out (debits, payments, fees), positive for money in.
- Numbers may use a decimal comma (1.234,56 = 1234.56) or a decimal point (1,234.56 = 1234.56).
- date: the booking date as YYYY-MM-DD.
- counterparty_iban: the other party's IBAN if printed (it may wrap onto the next line), else null.
- opening_balance / closing_balance: the statement's EUR opening and closing balance."""


def llm_parse(model, text=None, images=None):
    msg = {"role": "user", "content": PROMPT + ("\n\nSTATEMENT TEXT:\n" + text if text else "")}
    if images:
        msg["images"] = images
    body = json.dumps({"model": model, "messages": [msg], "format": SCHEMA, "stream": False,
                       "think": False, "keep_alive": "10m",
                       "options": {"temperature": 0, "num_ctx": 16384}}).encode()
    req = urllib.request.Request(OLLAMA + "/api/chat", body, {"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.load(r)
    dt = time.time() - t0
    m = out["message"]
    d = json.loads(m.get("content") or m.get("thinking") or "")  # qwen3-vl + think=false answers in "thinking"
    txns = [dict(date=x["date"], description=x["description"],
                 amount=Decimal(str(x["amount"])).quantize(Decimal("0.01")),
                 iban=(x.get("counterparty_iban") or None)) for x in d["transactions"]]
    return (Decimal(str(d["opening_balance"])).quantize(Decimal("0.01")),
            Decimal(str(d["closing_balance"])).quantize(Decimal("0.01")), txns, dt)


def page_images(path):
    with pdfplumber.open(path) as pdf:
        out = []
        for p in pdf.pages:
            buf = io.BytesIO()
            p.to_image(resolution=110).original.save(buf, format="PNG")
            out.append(base64.b64encode(buf.getvalue()).decode())
        return out

# ---------------------------------------------------------------- scoring

def score(ref, got):
    """Compare a parse against the reference parse. Returns a dict of aggregate numbers only."""
    r_open, r_close, r_tx = ref
    g_open, g_close, g_tx = got
    key = lambda x: (x["date"], x["amount"])
    rc, gc = collections.Counter(map(key, r_tx)), collections.Counter(map(key, g_tx))
    missing, extra = sum((rc - gc).values()), sum((gc - rc).values())
    ib_ref = {key(x): x["iban"] for x in r_tx if x["iban"]}
    ib_ok = sum(1 for x in g_tx if key(x) in ib_ref and (x["iban"] or "").replace(" ", "") == ib_ref[key(x)])
    return dict(
        rows=f"{len(g_tx)}/{len(r_tx)}", missing=missing, extra=extra,
        open_diff=g_open - r_open, close_diff=g_close - r_close,
        balance_check=(g_open + sum(x["amount"] for x in g_tx) == g_close),
        iban=f"{ib_ok}/{len(ib_ref)}",
    )


def verify_reference():
    """The hand parsers are the reference, so check them against independent evidence first."""
    print("== reference check (hand parsers vs the Statement's own totals / the Revolut CSV)")
    for bank, path in SAMPLES.items():
        o, c, tx = HAND[bank](text_of(path))
        out_ = -sum(x["amount"] for x in tx if x["amount"] < 0)
        in_ = sum(x["amount"] for x in tx if x["amount"] > 0)
        print(f"  {bank:10} rows={len(tx):3} out={out_} in={in_} "
              f"balance_check={o + in_ - out_ == c} ibans={sum(1 for x in tx if x['iban'])}")
    rows = [r for r in csv.DictReader(open(REVOLUT_CSV)) if r["Completed Date"].startswith("2026-09")]
    csv_keys = collections.Counter((r["Completed Date"][:10], Decimal(r["Amount"]) - Decimal(r["Fee"])) for r in rows)
    _, _, tx = parse_revolut(text_of(SAMPLES["revolut"]))
    pdf_keys = collections.Counter((x["date"], x["amount"]) for x in tx)
    print(f"  revolut vs CSV: identical (date, amount) multiset = {csv_keys == pdf_keys}")


def main(models):
    verify_reference()
    refs = {b: HAND[b](text_of(p)) for b, p in SAMPLES.items()}
    print("\n== LLM runs (scored against the reference)")
    for model in models:
        vision = model.endswith("+img")
        name = model.removesuffix("+img")
        for bank, path in SAMPLES.items():
            try:
                if vision:
                    o, c, tx, dt = llm_parse(name, images=page_images(path))
                else:
                    o, c, tx, dt = llm_parse(name, text=text_of(path))
                s = score(refs[bank], (o, c, tx))
                print(f"  {model:22} {bank:10} {dt:6.1f}s  " + "  ".join(f"{k}={v}" for k, v in s.items()))
            except Exception as e:  # prototype: report and move on
                print(f"  {model:22} {bank:10} ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    main(sys.argv[1:])
