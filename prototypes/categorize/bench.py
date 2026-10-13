"""PROTOTYPE — throwaway. Answers #6: how accurate and fast is a local Ollama model at suggesting
a Subcategory, which prompt shape works, and what confidence threshold sends a Transaction to
the Review queue?

Run:  .venv/bin/python prototypes/categorize/extract.py        (once)
      .venv/bin/python prototypes/categorize/bench.py MODEL [MODEL ...] [--shapes bare,detail,fewshot]
Reads samples/PROTOTYPE_transactions.json + samples/PROTOTYPE_gold_labels.csv (both gitignored),
writes per-Transaction results to samples/PROTOTYPE_results_<model>.json, prints aggregates only.

Confidence = the model's own probability of the Subcategory it emitted (product of the token
probabilities of the JSON value, from Ollama's logprobs), not a self-reported number.
"""
import csv, json, math, statistics, sys, time, urllib.request

OLLAMA = "http://192.168.50.188:11434"
TXNS = "samples/PROTOTYPE_transactions.json"
GOLD = "samples/PROTOTYPE_gold_labels.csv"

CATEGORIES = {  # #4 defaults
    "Food": ["Groceries", "Restaurants & cafés", "Fast food & takeaway", "Other"],
    "Home": ["Rent / mortgage", "Utilities", "Internet & phone", "Furniture & household", "Maintenance & repairs", "Other"],
    "Transport": ["Fuel", "Parking & tolls", "Car maintenance", "Car insurance & registration", "Public transport & car sharing", "Other"],
    "Health": ["Pharmacy", "Doctor & dental", "Health insurance", "Other"],
    "Children": ["Childcare & school", "Activities", "Clothes & toys", "Other"],
    "Shopping": ["Clothing & shoes", "Electronics", "Gifts", "Personal care", "Other"],
    "Leisure": ["Travel", "Hobbies & sport", "Entertainment & going out", "Subscriptions & digital services", "Other"],
    "Finance": ["Bank fees", "Insurance (non-health)", "Taxes & fines", "Other"],
    "Other": ["Cash withdrawal", "Payments to people", "Miscellaneous"],
    "Income": ["Salary", "Benefits & allowances", "Interest", "Gifts received", "Other income"],
}
SUBCATS = [f"{c} > {s}" for c, subs in CATEGORIES.items() for s in subs]
SCHEMA = {"type": "object", "properties": {"subcategory": {"type": "string", "enum": SUBCATS}},
          "required": ["subcategory"]}

SYSTEM = """You categorize one household bank Transaction (a family in Slovenia; merchant names and
purposes are often Slovenian) into exactly one Subcategory from this list:
{options}

Conventions of this household:
- Money in at a shop is a Refund: use the shop's spending Subcategory, not Income.
- Payments to a private person: categorize by purpose if the purpose text makes it clear,
  otherwise "Other > Payments to people".
- Cash withdrawals: "Other > Cash withdrawal".
Answer with JSON only."""


def describe(x, shape):
    amt = float(x["amount"])
    lines = [f"Direction: {'in' if amt > 0 else 'out'}", f"Amount: {abs(amt):.2f} EUR",
             f"Description: {x['description']}"]
    if shape != "bare" and x["detail"]:
        lines.append(f"Details: {x['detail']}")
    return "\n".join(lines)


def examples_for(x, labelled):
    """Few-shot = earlier manual corrections, leaving out the same merchant (that would be a Rule)."""
    seen, out = set(), []
    for y in labelled:
        if y["description"] == x["description"] or y["description"] in seen:
            continue
        seen.add(y["description"])
        d = f" ({y['detail']})" if y["detail"] else ""
        out.append(f"- {'in' if float(y['amount']) > 0 else 'out'} {y['description']}{d} -> {y['gold']}")
    return "Earlier corrections by this household (other merchants):\n" + "\n".join(out)


def ask(model, system, user):
    body = json.dumps({"model": model, "stream": False, "think": False, "keep_alive": "15m",
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                       "format": SCHEMA, "logprobs": True,
                       "options": {"temperature": 0, "num_ctx": 8192}}).encode()
    req = urllib.request.Request(OLLAMA + "/api/chat", body, {"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.load(r)
    dt = time.time() - t0
    text = out["message"].get("content") or out["message"].get("thinking") or ""
    answer = json.loads(text)["subcategory"]
    # confidence: sum the logprobs of the tokens that spell the answer inside the JSON
    lp, pos, start = 0.0, 0, text.find(answer)
    for t in out.get("logprobs") or []:
        if pos + len(t["token"]) > start and pos < start + len(answer):
            lp += t["logprob"]
        pos += len(t["token"])
    return answer, math.exp(lp), dt


def ask_claude(model, system, user):
    """Cloud reference only (not a v1 option): same prompt + enum schema, no logprobs -> conf=1."""
    import anthropic  # key from ANTHROPIC_API_KEY
    client = ask_claude.client = getattr(ask_claude, "client", None) or anthropic.Anthropic()
    t0 = time.time()
    r = client.beta.messages.create(
        model=model, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": dict(SCHEMA, additionalProperties=False)}},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    )
    if r.stop_reason == "refusal":
        return "REFUSED", 0.0, time.time() - t0
    text = next(b.text for b in r.content if b.type == "text")
    return json.loads(text)["subcategory"], 1.0, time.time() - t0


def load():
    txns = json.load(open(TXNS))
    gold = list(csv.DictReader(open(GOLD)))
    by_detail = {(g["bank"], g["description"], g["example_detail"]): g for g in gold}
    by_desc = {(g["bank"], g["description"]): g for g in gold}
    for x in txns:
        g = by_detail.get((x["bank"], x["description"], x["detail"])) or by_desc[(x["bank"], x["description"])]
        x["gold"], x["sure"] = g["gold"], g["sure"] == "sure"
    return [x for x in txns if x["gold"] != "TRANSFER"]  # Transfers never reach the LLM


def run(model, shape, txns):
    system = SYSTEM.format(options="\n".join(SUBCATS))
    users = []
    for x in txns:
        user = describe(x, shape)
        if shape == "fewshot":
            user = examples_for(x, txns) + "\n\nTransaction to categorize:\n" + user
        users.append(user)
    cache, res = {}, []
    if model.startswith("claude-"):  # cloud: parallel calls
        from concurrent.futures import ThreadPoolExecutor
        uniq = list(dict.fromkeys(users))
        with ThreadPoolExecutor(8) as ex:
            cache = dict(zip(uniq, ex.map(lambda u: ask_claude(model, system, u), uniq)))
    for x, user in zip(txns, users):
        if user not in cache:
            cache[user] = ask(model, system, user)
        ans, conf, dt = cache[user]
        res.append(dict(x, shape=shape, model=model, answer=ans, conf=conf, secs=dt))
    return res, [v[2] for v in cache.values()]


def report(res, secs):
    def acc(rs, cat=False):
        f = (lambda r: r["answer"].split(" > ")[0] == r["gold"].split(" > ")[0]) if cat else (lambda r: r["answer"] == r["gold"])
        return f"{sum(map(f, rs))}/{len(rs)} = {100 * sum(map(f, rs)) / max(1, len(rs)):.0f}%"
    first = {}
    for r in res:  # the LLM's real workload once Rules exist: one row per merchant
        first.setdefault(r["description"], r)
    first = list(first.values())
    sure = [r for r in res if r["sure"]]
    print(f"    all rows      subcat {acc(res):14} category {acc(res, True)}")
    print(f"    sure gold     subcat {acc(sure):14} category {acc(sure, True)}")
    print(f"    1 per merchant subcat {acc(first):13} category {acc(first, True)}")
    s = sorted(secs[1:] or secs)  # first call includes model load
    print(f"    latency/call  median {statistics.median(s):.2f}s  max {s[-1]:.2f}s  (first call {secs[0]:.1f}s)")
    print("    threshold  auto-accepted   accuracy of auto   wrong-but-auto   -> Review queue")
    for t in (0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99):
        auto = [r for r in res if r["conf"] >= t]
        ok = sum(r["answer"] == r["gold"] for r in auto)
        print(f"    {t:9.2f}  {len(auto):4}/{len(res):<4}     {100 * ok / max(1, len(auto)):5.0f}%"
              f"            {len(auto) - ok:4}             {len(res) - len(auto):4}")


def main(argv):
    shapes = ["bare", "detail", "fewshot"]
    if "--shapes" in argv:
        i = argv.index("--shapes"); shapes = argv[i + 1].split(","); argv = argv[:i] + argv[i + 2:]
    txns = load()
    print(f"{len(txns)} non-Transfer Transactions, {len({x['description'] for x in txns})} merchants, "
          f"{sum(x['sure'] for x in txns)} with sure gold labels")
    for model in argv:
        allres = []
        for shape in shapes:
            try:
                res, secs = run(model, shape, txns)
            except Exception as e:  # prototype: report and move on
                print(f"\n== {model} / {shape}: ERROR {type(e).__name__}: {e}"); continue
            allres += res
            print(f"\n== {model} / {shape}")
            report(res, secs)
        json.dump(allres, open(f"samples/PROTOTYPE_results_{model.replace(':', '_')}.json", "w"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
