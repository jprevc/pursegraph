---
status: superseded by ADR-0002
---

# Categorizers pull work through an API; the core has no LLM code

_Superseded by [ADR 0002](0002-no-bundled-categorizer-webhooks-say-when-transactions-wait.md): Pursegraph ships no Categorizer, and the outgoing webhook rejected below returns._

Some operators run Ollama on a separate machine that sleeps until it is woken, for example with Wake-on-LAN, and some want a different categorization service entirely. Pursegraph's core therefore no longer calls any LLM. It offers an API through which a Categorizer fetches the Transactions waiting for a Suggestion, with the context a prompt needs (the Subcategories and the Household's earlier manual corrections as examples), and sends back Suggestions with how sure it is. Admins give each Categorizer its own token, which can only do this. The core keeps the auto-accept threshold and the Review queue. The Ollama Categorizer that ships with Pursegraph uses only this API, and it does not wake anything.

## Considered Options

- **Built-in Wake-on-LAN in the worker.** Rejected because it covers only one way of making the LLM available. Also, a container on Docker Compose's default bridge network can't reliably broadcast onto the LAN.
- **An outgoing webhook ("LLM needed") from the core**, with the receiver waking the machine. Rejected once Categorizers pull: a Categorizer can poll from an always-on machine, and waking the LLM machine before categorizing is the Categorizer's job. The core then needs no delivery, retries or reachability checks.
- **Publishing to a message broker (MQTT and similar).** Rejected because it adds a service and a client library for a few events a week, and polling needs none of it.
- **Categorizers setting outcomes directly.** Rejected because the threshold and the Review queue are the Household's checkpoint against a misbehaving Categorizer.

## Consequences

- Transaction text leaves Pursegraph for wherever a Categorizer sends it, possibly a cloud service. Until now the README promised that it stayed on the LAN's Ollama. That is now the operator's choice, made when they create a token, and the token page says so.
- The core can't know whether an LLM is reachable. The admin LLM suggestions page shows what the core does know: how many Transactions are waiting and since when, and when the last Suggestion arrived and from which token. The sidebar's "Suggestions unavailable" and Check now are removed.
- Each Categorizer is responsible for its confidence being meaningful, because the auto-accept threshold applies to every Categorizer alike.
