# Conventions

The rules every skill in this repository follows, so they feel like one product and work in
as many agents as possible. `tests/repo/` checks the ones marked *(tested)*.

## The skill folder

- A skill is a standard [Agent Skills](https://agentskills.io) folder in `skills/<name>/`:
  `SKILL.md`, plus `references/`, `scripts/`, `examples/` or `assets/` as needed. Nothing
  else goes in it, since the whole folder is what users install and what the release zip
  holds. The guide for people goes in `docs/<name>.md`, the tests and a `README.md` for
  contributors in `tests/<name>/`.
- The folder name is the skill's `name`: lowercase words joined by hyphens *(tested)*.
- The frontmatter has `name` and `description`, and optionally `license`, `metadata` and
  `allowed-tools` *(tested)*. The description is what agents pick the skill by. Keep it
  short and in three parts: what the skill makes, what it reads from, then "Use when" with
  the phrases a user would actually type. At most 1,024 characters, without `<` or `>`
  *(tested)*.
- `SKILL.md` stays under 500 lines *(tested)*. Put detail in `references/` and say when to
  read it. Every file `SKILL.md` or a reference points to exists *(tested)*.

## Writing for the agent

- Write instructions, not documentation: what to do, in order, and how to tell it worked.
- Refer to the skill's own files as `<this skill's folder>/scripts/...`. Agents install
  skills in different places.
- Don't depend on one agent's features for an essential step. If a step uses something
  only some agents have, such as subagents, say what to do without it.
- Name MCP tools by what they do as well as by name, since tool names change.
- No em-dashes in skill text, guides or root documents *(tested)*. It keeps the agent's
  output plain.

## Scripts

- Scripts do the deterministic work: checking, measuring, laying out, keeping progress.
  The agent does the judging and calls the MCP servers, then hands results to the scripts.
  Scripts never call an MCP server.
- Python, standard library first. A script that needs a package declares it inline with a
  [`# /// script`](https://packaging.python.org/en/latest/specifications/inline-script-metadata/)
  block, so `uv run` installs it; a script imports nothing else *(tested)*. Prefer the
  standard library whenever it does the job: every dependency is something that can fail
  to install on a user's machine.
- Scripts only reach the network for hosts the skill's guide names, with timeouts, size
  limits and redirects kept to those hosts.
- Scripts fail loudly with a message the agent can act on, rather than guessing.
- Every script has tests in `tests/<name>/` that run offline.

## Working with Whimsical

- Build on a new board unless the user names an existing one, and give it a clear title.
- Use only IDs that came from the Whimsical MCP. Never make one up.
- After writing to a board, read it back and check the result before moving on.
- Credit sources on the board, as app-wireframe does for Mobbin.

## Files and data

- Working files go in a folder named after the task, in the folder the agent was started
  in. A skill never writes outside it, never overwrites the user's files, and can pick up
  a run that stopped halfway.
- Nothing is collected. The skills send data only to the services the user connected.
- Examples, tests and issues use fictional companies and people, such as Acme, Globex and
  Initech, never real customer data.

## The guide

`docs/<name>.md` is for people using the skill, and for agents setting it up for them. Every
guide has these sections, in this order *(tested)*, so a reader who knows one knows them all:

1. The cover, the `# Title` and the intro, as [On whimsical.com](#on-whimsicalcom) says.
2. `## What it reads from`: every source, the main one first.
3. `## What you'll get`.
4. `## Requirements`: what's needed, as bullets; anything optional last, starting "Optional:".
5. `## Install`: it opens with "The skill needs" and the MCP servers from its `marketplace.json`
   entry, with their URLs *(tested)*, then says what's optional. Then the three tabs, with the
   same steps as every other guide but the skill's name and servers *(tested)*.
6. `## Use it`: example prompts, then what the agent asks and where its files go.
7. `## How it works`.
8. `## Status`: how new the skill is, and where it's been tried.
9. `## Privacy`.
10. `## License`.

Sections only one skill needs (examples, questions, how a layout is chosen) go between these,
where they fit. Notes for contributors, such as the skill's files and how to test and try it,
go in `tests/<name>/README.md`, not in the guide.

A skill's `mcpServers` in `marketplace.json` lists only the servers its main use needs: the one
in the intro's prompt. A source it can read but doesn't need, like Linear for tech-tree, stays
out: the plugin would add it for everyone, and whimsical.com would show it as needed. The guide
covers it as optional.

## On whimsical.com

[whimsical.com/skills](https://whimsical.com/skills) lists every skill in the latest
release, built from this repository. Each skill's page shows:

- Its title, the guide's `# Title` line, which comes right after its cover: a guide starts
  with `![<headline>](covers/<name>.png)`, a blank line, then `# Title` *(tested)*.
- Its card description, the `description` in its `marketplace.json` entry.
- A summary, the guide's intro: everything before its first `##` heading. The intro starts
  with one paragraph saying what the skill does, then a ```` ```text ```` block with an
  example prompt *(tested)*, then whatever shows the result. Images and links in the intro
  can be relative; the site points them at GitHub.
- Its cover, `docs/covers/<name>.png`, made from `docs/covers/<name>.json` and
  `docs/covers/art/<name>.svg` *(tested)*.
  [docs/covers/README.md](docs/covers/README.md) explains how to make one.
- The MCP servers it connects to, from its `marketplace.json` entry.
- Its install steps, the guide's `## Install` section: the paragraph under the heading,
  then one tab per `### ` heading, named by the heading's text before any ` (` *(tested)*.
  Code blocks there get a copy button, so keep each one a set of commands to run as is.
- An example board, if the intro's image links to one: `[![alt](image.png)](board URL)`.

Keep the intro about what the skill does. Caveats, like how new the skill is, go in a
later section (`## Status`), so they stay in the guide but off the website.

The page's URL is `whimsical.com/skills/<name>`, so renaming a skill breaks its link.

## Versions

- Each skill's version is in its `.claude-plugin/marketplace.json` entry. Bump it in the
  same pull request as the change: patch for fixes, minor for new abilities, major when
  users have to do something differently.
