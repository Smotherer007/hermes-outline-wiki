# hermes-outline-wiki

Outline wiki plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

With it, Hermes can search, read, write, organise and comment on documents in your [Outline](https://www.getoutline.com/) knowledge base, from the CLI or from any gateway chat (Teams, Slack, Telegram, ...). It works with Outline cloud (`yourteam.getoutline.com`) and with self-hosted installations, and it can work with several workspaces at once.

This is the Hermes port of [pi-outline-wiki](https://github.com/Smotherer007/pi-outline-wiki). The tools, their parameters, the skills and the config file format are the same, so an agent (or a person) who knows one can use the other.

## Installation

```bash
hermes plugins install Smotherer007/hermes-outline-wiki
hermes plugins enable outline-wiki
```

For development, clone the repository and install it from a local path:

```bash
git clone https://github.com/Smotherer007/hermes-outline-wiki
hermes plugins install file://$PWD/hermes-outline-wiki --enable
```

The plugin uses only the Python standard library. It adds no packages to Hermes' virtualenv.

## Quick start

1. In Outline, go to **Settings -> API & Apps** and create an API key. It starts with `ol_api_`.
2. Configure the workspace. You can ask Hermes to run `outline_setup`, or set it up without the model (see [Configuration](#configuration)).
3. Ask Hermes about your wiki, or use `/wiki <topic>`.

```yaml
outline_setup:
  name: work
  url: https://acme.getoutline.com
  apiKey: ol_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  description: internal engineering wiki
```

`outline_setup` checks the connection right away and reports the workspace and the authenticated user. A typo in the URL or key shows up immediately instead of on the first real call.

The `url` does not have to be exact. A bare host, a trailing slash, a pasted `/api` base or the `/mcp` endpoint from Outline's MCP docs all end up as the workspace root.

## Tools

All tools belong to the `outline` toolset.

| Tool | Description |
|------|-------------|
| `outline_setup` | Configure workspace URL and API key. |
| `outline_status` | Show configured profiles and verify the active key still works. |
| `outline_profile` | List, switch, or delete workspace profiles, with what each wiki holds. |
| `outline_collections` | List collections with their ids. |
| `outline_structure` | Show the nested document tree of one collection. |
| `outline_search` | Full-text search with optional collection, status and date filters. Can search all workspaces at once. |
| `outline_list` | Browse documents: recent, by collection, by parent, or your drafts. |
| `outline_read` | Read a document's markdown body, optionally with its children or saved to a file. |
| `outline_create` | Create a document in a collection or under a parent document. |
| `outline_update` | Replace, append to, or prepend to a document; rename it; publish a draft. |
| `outline_move` | Move a document into another collection or under another parent. |
| `outline_archive` | Archive, restore, or unpublish a document. |
| `outline_delete` | Move a document to the trash, or delete it permanently. |
| `outline_comments` | Read comment threads on a document, nested by reply. |
| `outline_comment` | Post a comment or reply on a document. |
| `outline_export` | Export a document or a whole collection to local markdown files. |

Each tool returns JSON. `result` holds the text for the model, and the other keys hold structured details such as ids and counts. On failure the tool returns `{"error": "..."}` and never raises.

### Searching

```yaml
outline_search:
  query: postgres failover
  # collectionId: <id>              # restrict to one collection
  # statusFilter: [published, archived]
  # dateFilter: month               # only recently updated documents
```

Archived documents are left out unless you ask for them with `statusFilter`.

With several workspaces configured, `allProfiles: true` searches all of them in parallel and labels each hit with the workspace it came from. `allProfiles` cannot be combined with `profile`, `collectionId` or `documentId`, because those only mean something in one workspace. The tool rejects such a combination instead of silently returning nothing.

### Reading, writing and retiring pages

- `outline_read` truncates long pages at 20,000 characters by default. Set `maxChars: 0` to read the whole page. `saveDir` also writes the full page to a `.md` file.
- `outline_create` publishes into a collection by default. `parentDocumentId` nests the page under another one, and `publish: false` keeps it as a personal draft. Don't repeat the title as a heading in `text`: Outline renders the title separately.
- `outline_update` defaults to `mode: replace`, which overwrites the whole body. `append` and `prepend` add to a page without reading it and sending it back.
- `outline_archive` is the reversible way to retire a page. `outline_delete` moves a page to the trash, and `permanent: true` erases it for good.
- `outline_export` writes markdown files straight to disk. That costs far less than reading page after page through the model.

## Slash commands

| Command | Description |
|---------|-------------|
| `/wiki <topic>` | Search the wiki and summarise what it says, with citations. |
| `/wiki-capture [focus]` | Write the durable knowledge from this session into the wiki. |

Both commands start an agent turn with a prepared prompt. They always work in the CLI. In the gateway, Hermes only lets plugins start turns if you allow it:

```yaml
# config.yaml
plugins:
  entries:
    outline-wiki:
      allow_gateway_injection: true
```

Without that setting, the command answers with the prompt, and you can send it as a normal message.

## Skills

The plugin ships three skills. They teach the agent how to use the wiki well, not just which tools exist.

| Skill | Purpose |
|-------|---------|
| `outline-wiki:outline-wiki` | Research the wiki before answering questions about internal systems, conventions and decisions. |
| `outline-wiki:outline-doc-writing` | Where a page belongs, how to structure it, and how to update it without destroying other people's work. |
| `outline-wiki:outline-knowledge-capture` | Turn what was worked out in a session into a durable page: decision records, incident findings, gotchas. |

Hermes keeps plugin skills out of its skill index. To make up for that, the plugin adds a short section to the system prompt. It points the agent to the three skills and lists the configured workspaces with their descriptions. The section contains no keys.

The repository also works as a skills tap, if you want the skills in other Hermes setups without the plugin:

```bash
hermes skills tap add Smotherer007/hermes-outline-wiki
hermes skills install Smotherer007/hermes-outline-wiki/outline-wiki
```

These skills declare `requires_toolsets: [outline]`, so they stay hidden while the plugin's tools are not available.

## Configuration

A workspace can be configured in any of three ways. All of them can be combined.

### 1. The `outline_setup` tool

`outline_setup` writes `$HERMES_HOME/outline-config.json`, atomically and with mode `0600`. `HERMES_HOME` is separate for each Hermes profile, so every Hermes profile gets its own set of wikis. `OUTLINE_CONFIG` points the plugin at a different file.

### 2. The config file

The file format is the same as in pi-outline-wiki. If you already use the pi extension, copy the file over:

```bash
cp ~/.pi/outline-config.json ~/.hermes/outline-config.json
```

```json
{
  "profiles": {
    "work": {
      "url": "https://acme.getoutline.com",
      "apiKey": "ol_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "description": "internal engineering wiki"
    }
  },
  "activeProfile": "work"
}
```

The plugin rereads the file when it changes. A profile you add from the CLI therefore shows up in a running gateway.

### 3. Environment variables

These suit containers, where secrets arrive as environment variables and should not end up in a file the agent can edit.

| Variable | Meaning |
|----------|---------|
| `OUTLINE_URL` | Workspace URL |
| `OUTLINE_API_KEY` | API key |
| `OUTLINE_DESCRIPTION` | Optional one-liner on what the wiki holds |
| `OUTLINE_PROFILE_NAME` | Profile name, default `default` |
| `OUTLINE_CONFIG` | Path of the profile file |

The environment profile lives only in memory. It is never written to the file and cannot be deleted with `outline_profile`. If the file has a profile with the same name, the file wins.

### Multiple workspaces

Call `outline_setup` once for each wiki, each time with a different `name`. The first profile becomes active, and later ones don't take over the active slot.

**Give every workspace a `description`.** `outline_profile`, `outline_status` and the system prompt section all show it. It is how the agent decides which wiki to search, instead of guessing from a profile name. The skills tell the agent to ask you before a write whenever it could land in the wrong wiki.

| Need | How |
|------|-----|
| See what is configured | `outline_profile` |
| Switch the default | `outline_profile: { action: use, name: kunde-a }` |
| One call against another wiki | any tool + `profile: kunde-a` |
| Search everything at once | `outline_search` + `allProfiles: true` |

Document ids only exist within their workspace. If a fan-out search reports a hit as `profile kunde-a`, read it with `outline_read` and `profile: kunde-a`.

### Safety level

`safety_level` controls the tools that change the wiki: create, update, move, archive, delete and comment.

| Value | Effect |
|-------|--------|
| `open` (default) | Write tools run directly, as in pi-outline-wiki. |
| `confirm` | Every write goes through Hermes' approval gate. In a chat that means the usual approval prompt. A denial or a timeout blocks the call. |
| `readonly` | Write tools are blocked. |

```bash
hermes config set plugins.entries.outline-wiki.settings.safety_level confirm
```

The setting also shows up as a dropdown in the Desktop app under **Capabilities -> Plugins**. It applies from the next tool call on, with no restart. Reads and the local-only tools (setup, profile, export) are never affected.

### Self-hosted instances

Point `url` at your installation, for example `https://wiki.example.com` or `http://localhost:3000`. If the instance uses a self-signed certificate, set `insecureTls: true` in `outline_setup`. Unlike the pi extension, this turns off certificate validation only for that profile's requests, not for the whole process. `outline_status` warns as long as it is on.

### Permissions

The plugin acts as the user who owns the API key. It can only see and change what that user can see and change in Outline. You control access by choosing which account the key belongs to.

## Development

```bash
python -m pip install pytest pyyaml
python -m pytest tests

# check the plugin the way Hermes loads it
hermes plugins doctor . --ci
hermes plugins validate .
```

The tests import the plugin the way Hermes does: as a package whose `__init__.py` is the repository root. They talk to a small Outline stand-in on localhost, so every request goes through the real HTTP client.

The layout follows the pi extension:

| Path | Content |
|------|---------|
| `models.py` | plain frozen dataclasses |
| `client.py` | all HTTP, standard library only |
| `formatters.py` | pure display functions |
| `config.py` | profile store |
| `tools/` | one module per tool, each with `SCHEMA` and `handle` |
| `safety.py` | safety level (`pre_tool_call` hook) |
| `commands.py` | `/wiki` and `/wiki-capture` |
| `skills/` | the three skills, also usable as a tap |

## License

MIT
