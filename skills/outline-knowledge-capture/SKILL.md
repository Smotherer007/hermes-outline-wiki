---
name: outline-knowledge-capture
description: Turn what was worked out in a coding session into a durable Outline wiki page - architecture decisions, debugging findings, incident write-ups, setup and runbook steps, or gotchas that cost real time. Use when the user says "write this up", "document this decision", "capture this in the wiki", "add this to our docs", "so we don't hit this again", or after any session that produced knowledge which is not obvious from the code alone.
allowed-tools: outline_profile, outline_collections, outline_structure, outline_search, outline_read, outline_create, outline_update, outline_comment
version: 1.0.0
metadata:
  hermes:
    tags: [outline, wiki, documentation]
    requires_toolsets: [outline]
---

# Capturing session knowledge in Outline

Sessions produce two kinds of output: the change to the code, and the
understanding that made the change possible. The second one is lost unless
someone writes it down. That is what this is for.

## What is worth capturing

Write it up when the finding is **durable and non-obvious**:

- a decision with alternatives that were rejected for reasons
- a root cause that took real effort to find
- an environment or setup step that is not in any README
- a constraint that is invisible in the code ("the vendor API rate-limits
  per organisation, not per key")
- a workaround and the condition under which it can be removed

Do not write up: routine changes the diff already explains, transcripts of
what you tried, or anything you would have to invent details for.

## Procedure

1. **Pick the workspace.** If `outline_profile` shows more than one, decide
   which wiki this belongs in before writing anything, and pass `profile`
   explicitly on every call. Work done for a client belongs in that client's
   workspace - never in the internal wiki or another client's, even when the
   technical finding is general. If the session touched more than one context
   and you cannot tell, ask.
2. **Check for an existing home.** `outline_search` with the system or
   component name. A decision about the payments service belongs on or under
   the payments page, not in a new orphan document.
3. **Extend before you create.** If a relevant page exists, `outline_read` it
   and add a dated section with `outline_update` `mode: append`.
4. **Otherwise create.** `outline_collections` -> `outline_structure` ->
   `outline_create` under the right parent.
5. **Report back** with the workspace, title, id and URL.

## What to write

Answer the four questions a future colleague will actually have:

- **What was the situation?** One paragraph of context, with dates and
  version or commit references where they matter.
- **What did we decide or find?** The conclusion, stated plainly and up front.
- **Why?** The reasoning, and what was ruled out. This is the part that
  cannot be reconstructed from the repository later.
- **What now?** Consequences, follow-ups, and how to tell if this stops being
  true.

Include the concrete artefacts: the exact error message, the command that
reproduces it, the file paths, the ticket or PR link. Leave out credentials,
tokens and customer data - a wiki page is readable by everyone in that
workspace. A page that says "we
fixed a timeout issue" helps nobody.

## Templates

**Decision (append to the component's page, or a new child page)**

```
## <Decision> - <YYYY-MM-DD>

**Context.** <what forced the choice>
**Decision.** <what we chose>
**Alternatives.** <option: why it lost>
**Consequences.** <what this makes easy, what it makes hard, what to revisit>
```

**Debugging / incident finding**

```
## <Symptom> - <YYYY-MM-DD>

**Symptom.** <what was observed, with the exact error>
**Root cause.** <the actual mechanism>
**Fix.** <what was changed, with paths or PR link>
**How to spot it again.** <the signal that identifies this failure mode>
```

**Gotcha**

```
## <Short name>

<One paragraph: what surprises people, and what to do instead.>
```

## Tone and honesty

Write in the team's voice, not as a report about an AI session - drop
"I asked", "the agent", "in this conversation". State facts you verified;
mark anything uncertain as uncertain. If a conclusion is genuinely a
judgement call the team still has to make, `outline_comment` the open
question on the page rather than writing it up as settled.
