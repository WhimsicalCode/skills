# Conventions

The rules every skill in this repository follows, so they feel like one product and work in
as many agents as possible. `tests/repo/` checks the ones marked *(tested)*.

## The skill folder

- A skill is a standard [Agent Skills](https://agentskills.io) folder in `skills/<name>/`:
  `SKILL.md`, plus `references/`, `scripts/`, `examples/` or `assets/` as needed. Nothing
  else goes in it, since the whole folder is what users install and what the release zip
  holds. The guide for people goes in `docs/<name>.md`, the tests in `tests/<name>/`.
- The folder name is the skill's `name`: lowercase words joined by hyphens *(tested)*.
- The frontmatter has `name` and `description`, and optionally `license`, `metadata` and
  `allowed-tools` *(tested)*. The description says what the skill does and when to use
  it, with the phrases a user would actually type, in at most 1,024 characters and without
  `<` or `>` *(tested)*.
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

## Versions

- Each skill's version is in its `.claude-plugin/marketplace.json` entry. Bump it in the
  same pull request as the change: patch for fixes, minor for new abilities, major when
  users have to do something differently.
