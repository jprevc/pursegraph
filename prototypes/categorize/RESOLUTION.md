## Resolution

**Verdict: qwen3-vl:8b (local), few-shot prompt including the detail line, auto-accept only when the model's logprob confidence is ≥ 0.90. Everything else goes to the Review queue. Each manual correction becomes both a Rule and a few-shot example.**

Prototype (throwaway): [`prototypes/categorize/` on `prototype/llm-categorization`](https://github.com/jprevc/pursegraph/tree/prototype/llm-categorization/prototypes/categorize). `extract.py` turns the gitignored samples into Transactions, and `bench.py MODEL…` scores them against a gitignored answer key that a Member checked. The scripts print only aggregate numbers.

### Setup
- **Test set:** 132 non-Transfer Transactions with 77 distinct merchants, from Sparkasse SI, Revolut and N26. Transfers are left out because they never reach the LLM.
- **Output:** Ollama JSON-schema output whose `enum` is the 47 Subcategories from #4, so the model can't invent a Subcategory.
- **Confidence:** the model's own probability for the Subcategory it emitted (the product of the token probabilities from Ollama `logprobs`, Ollama 0.32.5), not a number the model reports about itself.
- **Prompt shapes:**
  - **bare:** name, direction and amount.
  - **detail:** bare plus the extra text the parser saw (Revolut's `To:` merchant line, Sparkasse's purpose, N26's own category).
  - **fewshot:** detail plus the household's corrections for *other* merchants (same-merchant history would be a Rule, not an example).
- **"First-time merchant"** means one row per merchant. This is the real workload once Rules exist, because repeat merchants never reach the LLM.

### Results (few-shot prompt, the best shape for every model)

| Model | All rows | First-time merchant | Per call | Auto-accept at | Auto-accepted | Wrong among auto |
|---|---|---|---|---|---|---|
| Claude Opus 5.5 (cloud, reference only) | 93% | 91% | 1.9 s | n/a (no logprobs) | – | – |
| qwen3:8b | 74% | 65% | 0.8 s | ≥ 0.99 | 73% | 10% |
| **qwen3-vl:8b** | 70% | 61% | 1.5 s | **≥ 0.90** | **67%** | **4%** (4 of 89) |
| gemma3:4b | 72% | 62% | 1.2 s | ≥ 0.99 | 70% | 18% |
| qwen2.5vl:7b | 67% | 56% | 1.1 s | ≥ 0.95 | 32% | 0% |
| qwen2.5vl:3b | 44% | 42% | 0.4 s | – | – | – |

- **Prompt shape:** detail adds 0–3 points over bare. Few-shot adds a further 5–10 points on every model above 3B.
- **Speed is a non-issue:** about 1 s per Transaction plus 15–30 s to load the model once, so under a minute for a Statement on the RTX 3070 Ti.
- **The local models are close to each other on accuracy (65–70%) and about 25 points behind Opus.** Their typical failure is not knowing local merchants. Examples: a DIY store filed under restaurants, a furniture store under electronics, a mountain hut under utilities. More local-model tuning won't close that gap. The household's corrections do: Rules for repeat merchants, few-shot examples for the household's conventions.
- **Calibration, not accuracy, picks the model.**
  - With qwen3:8b and gemma3, being wrong and being confident go together too often: even at ≥ 0.99, 10–18% of auto-accepted rows are wrong.
  - qwen3-vl:8b's confidence tracks correctness, giving a usable threshold.
  - qwen2.5vl:7b is the most cautious: it sends too much to the Review queue.

### Decisions
1. **Model:** `qwen3-vl:8b`. It's already installed, and its confidence is well calibrated.
2. **Prompt shape:**
   - Content: the 47 Subcategories as a JSON-schema `enum`, the household conventions from #4 (Refunds, payments to people, cash), and the Transaction's direction, amount, description and detail text.
   - Few-shot examples: the household's latest correction for each *other* merchant.
   - Settings: `think: false`, `temperature: 0`, `logprobs: true`.
3. **Threshold:**
   - Auto-accept (`source = llm`) when confidence ≥ 0.90. On this data that resolves about two thirds of what reaches the LLM, with about 4% wrong.
   - Below the threshold, the suggestion is stored as `suggested_subcategory` + `confidence` (#9), and the Transaction goes to the Review queue with the suggestion pre-selected.
   - The 0.90 lives in the installation settings table (#9), so it can be retuned per model.
4. **Corrections feed back in two ways.**
   - **A Rule:** every manual correction offers to create one (exact merchant, from #9), so the merchant never reaches the LLM again. On this sample, 55 of 132 rows were repeat merchants.
   - **A few-shot example:** the correction is also kept as an example. These teach the household's conventions for merchants the model hasn't seen; corrections to other merchants are worth about 5–10 points.
   - Both come from the stored outcomes, so nothing extra needs storing.
5. **Parsers must keep the categorization context in `raw`:** Sparkasse's purpose line ("Namen plačila"), N26's category line, Revolut's `To:` merchant line. Separately, the #5 Sparkasse parser drops the description of the interest row ("Pozitivne obresti"), which sits on the value-date line; fix that in the real parser.

### Caveats
- **The few-shot gains assume a mature history.** The few-shot runs used the corrections for all 76 other merchants, as if the household had used the app for months. A fresh installation starts nearer the *detail* numbers (about 55% on first-time merchants).
- **The sample is small:** 132 rows, 77 merchants. Re-check the threshold once real usage builds a bigger corrected set. The bench script can be rerun against the database's `manual` outcomes.
- **Cloud stays out of v1.** Claude Opus 5.5 (91% on first-time merchants) was run only as a reference. A cloud backend would send real Transaction text off the LAN and contradicts the map's frame.
