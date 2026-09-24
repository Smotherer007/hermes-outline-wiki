---
name: outline-wiki
description: Research the team's Outline wiki - or wikis - before answering questions about internal systems, conventions, decisions, runbooks or onboarding. Use whenever a question is about "how we do it here" rather than about general knowledge or the code in front of you - for example architecture decisions, deployment steps, naming conventions, ownership, incident history, or anything the user refers to as "the wiki", "our docs", "Confluence-style notes" or Outline. Also use it to check whether the wiki already covers something before writing a new page.
allowed-tools: outline_status, outline_profile, outline_collections, outline_structure, outline_search, outline_list, outline_read, outline_comments, outline_export
version: 1.0.0
metadata:
  hermes:
    tags: [outline, wiki, documentation]
    requires_toolsets: [outline]
---

# Researching the Outline wiki

The wiki is the team's memory. Code says what the system does; the wiki says
why, who owns it, and what was already tried. Read it before guessing.

## When to reach for it

Use the wiki when the answer depends on this organisation:

- "How do we deploy X?" / "What is our release process?"
- "Why did we choose Y?" / "Is there a decision record for this?"
- "Who owns service Z?"
- "What is our convention for naming / branching / logging?"
- The user mentions a page, a runbook, an ADR, or onboarding notes.

Do **not** use it for general programming questions, or for facts that the
repository in front of you answers directly.

## Which wiki

More than one Outline workspace can be configured, and they are separate
worlds: a document id from one is meaningless in another.

**Start with `outline_profile`** when you have not already seen the list this
session. It shows every configured workspace with a one-line description of
what it holds, and marks the active one. Then decide:

- The question clearly belongs to one workspace (the description names the
  client, product or team): search that one with `profile: <name>`.
- You do not know which workspace holds the answer: `outline_search` with
  `allProfiles: true` searches all of them at once and labels each hit with
  the workspace it came from.
- Only one workspace is configured: ignore all of this and just search.

After a fan-out, **carry the profile through**. A hit reported as
`profile kunde-a` must be read with `outline_read` and `profile: "kunde-a"`,
or you will get "document not found" from the wrong wiki.

If a workspace has no description, say so once and suggest the user re-run
`outline_setup` with one - without it you are guessing from the name.

## The loop

1. **Pick the wiki** (above), if more than one is configured.
2. **Search, do not browse.** `outline_search` with two or three distinctive
   nouns. "postgres failover" beats "how does our database failover work".
3. **Read the top hits.** The search snippet is not the answer.
   `outline_read` on the one or two most promising ids - with the same
   `profile` the hit came from.
4. **Follow the structure.** If a page looks like an index, use
   `outline_read` with `includeChildren: true`, or `outline_structure` on its
   collection, to see what sits under it.
5. **Answer with citations.** Name the document title, id and - when several
   workspaces are in play - the workspace you took it from. If several pages
   disagree, say so and give the update dates: wikis rot.

## Search that actually finds things

- Start broad, then filter. Only add `collectionId` after
  `outline_collections` told you which collection is relevant.
- If a search returns nothing, try a synonym, an acronym, and the spelled-out
  form before concluding the wiki is silent. Teams write "k8s" and
  "Kubernetes" in different pages.
- Recent-work questions ("what changed lately?") are `outline_list`, not
  `outline_search`. `outline_list` works on one workspace at a time.
- `allProfiles` cannot be combined with `collectionId` or `documentId`: those
  ids only exist in one workspace. Narrow the workspace first, then filter.
- Something that existed but is gone is usually archived, not deleted:
  re-run the search with `statusFilter: ["published", "archived"]`.

## Ids

Every tool takes a document id, and ids are scoped to one workspace. They
come from search, list or structure output - never invent one, and never
carry one from one workspace to another. An Outline URL like
`https://acme.getoutline.com/doc/runbook-deploy-aBc123XyZ` also works: pass
the trailing `runbook-deploy-aBc123XyZ` slug as `id`.

## Honesty rules

- If the wiki has nothing on the topic, say "the wiki does not cover this"
  rather than filling the gap with plausible-sounding invention.
- Distinguish what the wiki claims from what you verified in the code. A page
  last updated two years ago is a hypothesis, not a fact.
- Check `outline_comments` on a page before treating it as settled; open
  questions and corrections often live in the comments, not the body.

## Pulling content into the repo

When the user wants wiki content available offline or in the repository, use
`outline_export` with a `targetDir` instead of reading page after page
through the model - it writes markdown files directly and costs no context.
