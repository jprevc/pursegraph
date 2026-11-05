# Coding standards

What a review checks a diff against. `scripts/check` already enforces lint, format, types, one-line template comments and runtime imports, so a review skips those.

## Sources

- **`CONTEXT.md`**: code, docstrings, test names and UI copy use its terms, capitalised as it writes them, and none of its _Avoid_ terms.
- **`DESIGN.md` › Do's and Don'ts** and **`docs/design/<surface>.md`** for each surface the diff touches. `docs/agents/design-docs.md` says how to read them by section.
- **`docs/adr/`**: an ADR the diff contradicts is a finding.

## Rules

Each is a judgement call: report it with the hunk and the reason.

- **Spec in step:** a change to how a surface looks or behaves updates its `docs/design/<surface>.md` in the same diff, and the spec describes what was built.
- **One home for shared logic:** when the diff adds logic that already exists elsewhere (a JS handler, a template block, a fallback such as a Member's name-or-username), list the existing copies and say where the shared version should live: a model property, an included template, a script loaded in `base.html`.
- **A class belongs to its surface:** a class a template uses is defined in that surface's section of `static/pursegraph.css` or is a shared component. Reusing another surface's class carries its styles along. The period stepper reused `.step`, the Get started card's class, and its padding pushed the arrow out of place (#177).
- **Test names say what the test checks:** a name that claims more than the assertions check (e.g. "is saved" when it checks an attribute) is a finding.
- **Comments read without the diff:** a comment says what the code is or why it is that way. It doesn't say what changed or what the code used to be.
