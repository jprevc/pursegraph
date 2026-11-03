---
status: accepted
---

# Pursegraph ships no Categorizer; Webhooks say when Transactions are waiting

This supersedes [ADR 0001](0001-categorizers-pull-suggestions-through-an-api.md), which assumed that an Ollama Categorizer ships with Pursegraph and rejected an outgoing webhook. Pursegraph's core calls no LLM, and Pursegraph ships no Categorizer either: none in the app, the Compose stack or a shipped script. The core keeps Rules, Transfer detection, the auto-accept threshold and the Review queue. It still offers the Categorizer API from ADR 0001: a Categorizer fetches the Transactions waiting for a Suggestion with a token of its own and sends Suggestions back. Nothing on the operator's side is guaranteed to be polling, and a Categorizer on a machine that sleeps can't poll at all. So when an action leaves Transactions waiting, the core calls the admin's **Webhooks**. The call says only how many are waiting, and the receiver fetches them through the API.

## Considered Options

- **Shipping an Ollama Categorizer**, as a Compose service or a script (ADR 0001's plan). Rejected because it ties every install to one LLM runtime and one way of making it available, and Pursegraph would have to maintain its prompt, model and confidence. The docs ship an Ollama Categorizer instead, as a copyable example: `docs/examples/ollama_categorizer.py` receives the Webhook, and CI runs it against Pursegraph with Ollama faked so it keeps working.
- **Relying on Categorizers to poll** (ADR 0001's reason for rejecting the webhook). Rejected because polling needs an always-on machine on the operator's side, and with no bundled Categorizer nothing guarantees one. A Categorizer that can poll cheaply may still fetch now and then, as a backstop for a lost delivery.
- **Putting the waiting Transactions in the Webhook's payload.** Rejected because the receiver often isn't the Categorizer (for example, Home Assistant waking the machine the Categorizer runs on), so Transaction text would reach something that has no token. A count is enough to say "go fetch".
- **One Webhook per Categorizer token.** Rejected for the same reason: the receiver and the Categorizer are often different things. Webhooks are listed on the Categorizers page on their own, and every firing goes to all of them.
- **Signing deliveries with HMAC.** Rejected because Home Assistant's webhook trigger can't check a signature. The secret is in the URL instead. A forged call can at most make a Categorizer fetch with its own token.
- **Retrying failed deliveries.** Rejected because the core has no background worker. Each delivery is one POST with a 5 s timeout. An admin resends with Notify now, and the page shows each Webhook's latest attempt.
- **Publishing to a message broker (MQTT and similar).** Still rejected, as in ADR 0001: it adds a service and a client library for a few events a week.
- **Categorizers setting outcomes directly.** Still rejected, as in ADR 0001: the threshold and the Review queue are the Household's checkpoint against a misbehaving Categorizer.

## Consequences

- An install with no Categorizer connected works: the Transactions no Rule resolves wait in the Review queue without Suggestions. An install upgraded from the bundled Ollama gets no Suggestions until its operator connects a Categorizer, and must run `docker compose up -d --remove-orphans` so the old `categorize_worker` container stops.
- Transaction text leaves Pursegraph only through a Categorizer an admin gives a token to. Pursegraph doesn't restrict where that Categorizer runs, since it couldn't enforce that against a token holder, so the README no longer promises "LAN only".
- "LLM" no longer names anything in the app. An outcome set from a Suggestion is recorded as set by a Categorizer, and the admin page is called Suggestions.
- A delivery may be lost, and an action fires once without combining with the others. Receivers treat each delivery as "go fetch", which is safe to repeat.
- The core can't tell whether a Categorizer is reachable. It shows what it knows: how many Transactions are waiting and since when, when the last Suggestion arrived, and each Webhook's latest attempt.
- Each Categorizer is responsible for its confidence being meaningful, because the auto-accept threshold applies to every Categorizer alike.
