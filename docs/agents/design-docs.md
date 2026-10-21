# Reading the design docs

Every file read stays in context for the rest of the session and is paid for again on every turn. Read the sections your work touches, not whole files.

- **`DESIGN.md`**: the first ~230 lines are YAML frontmatter, impeccable's machine-readable token layer. It mirrors the `:root` tokens in `static/pursegraph.css`, so skip it. List the headings with `grep -n '^#' DESIGN.md`, then read only the sections you need with `sed -n`.
- **`docs/design/<surface>.md`**: one spec per page-level surface, listed under DESIGN.md's "Surfaces" heading. Read the ones your ticket names.
- **`static/pursegraph.css`**: list its sections with `grep -n '^/\* ---' static/pursegraph.css`, or grep for the selector, then read that range.
- **Prototypes**: once a variant is picked, the `docs/design` file is the spec. Grep the prototype for the snippet you need (`git show origin/prototype/<n>-<slug>:prototypes/<n>-<slug>/index.html | grep -n ...`). Read only that range, never the whole page.
