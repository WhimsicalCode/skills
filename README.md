# Whimsical skills

Skills that let your AI agent build [Whimsical](https://whimsical.com) boards for you,
through the [Whimsical MCP](https://whimsical.com/learn/integrations/mcp). Each one is a
standard [Agent Skills](https://agentskills.io) folder, so it works in Claude, Cursor,
Codex, GitHub Copilot, Gemini CLI and other agents that read skills.

| Skill | What it does | Try |
| --- | --- | --- |
| [App Wireframe](docs/app-wireframe.md) | Turns any app into editable lo-fi wireframes: name an app to pull its screens from Mobbin, or bring your own screenshots. [See 20 example boards](https://whimsical.com/templates/wireframes). | `Make wireframes of Airbnb` |
| [Renewal Timeline](docs/renewal-timeline.md) | Turns a customer's renewal emails into a timeline of every offer and counter-offer, with a pricing table, and writes the renewal summary: terms, NRR, usage, open items. | `Build the renewal timeline for Initech` |

These skills are new, and mostly written with coding agents. If something breaks in your
setup, please [open an issue](https://github.com/WhimsicalCode/skills/issues/new/choose).

## Install

Every skill needs the Whimsical MCP, and some need another MCP server too. Each skill's
guide, linked above, lists them and covers the rest of the setup.

### Claude Code

With [Node.js](https://nodejs.org) installed, run this in a terminal, with the skill's
name, then add the Whimsical MCP:

```sh
npx skills add WhimsicalCode/skills --skill app-wireframe --agent claude-code -g
claude mcp add --transport http --scope user whimsical https://mcp.whimsical.com/mcp
```

`-g` makes the skill available in every folder. Add any other MCP server the skill's guide
lists the same way, and skip the ones `claude mcp list` already shows. Then start Claude
Code, run `/mcp` and sign in.

Or install it as a plugin, which adds the MCP servers for you:

```text
/plugin marketplace add WhimsicalCode/skills
/plugin install app-wireframe@whimsical
```

### Claude apps (claude.ai and the desktop app)

1. Download the skill's zip from the
   [latest release](https://github.com/WhimsicalCode/skills/releases/latest), for example
   [`app-wireframe.zip`](https://github.com/WhimsicalCode/skills/releases/latest/download/app-wireframe.zip).
2. In Claude, open **Customize** (on claude.ai, [claude.ai/customize/skills](https://claude.ai/customize/skills)),
   click **Add**, then **Upload skill**, drop the zip and click **Upload**.
3. Still in **Customize**, under **Connectors**, add Whimsical and any other connector
   the skill's guide lists.

### Cursor, Codex, GitHub Copilot, Gemini CLI and other agents

With [Node.js](https://nodejs.org) installed, run this in a terminal, with the skill's
name and your agent:

```sh
npx skills add WhimsicalCode/skills --skill app-wireframe --agent cursor -g
```

Replace `cursor` with `codex`, `github-copilot`, `gemini-cli` or
[another agent's name](https://github.com/vercel-labs/skills/blob/main/docs/agents.md).
This copies the skill where your agent looks for skills, using the open
[skills](https://github.com/vercel-labs/skills) installer. Without Node.js, unzip the
skill's zip from the [latest release](https://github.com/WhimsicalCode/skills/releases/latest)
into that folder yourself. Either way, then add the MCP servers the skill's guide lists,
following your agent's MCP setup guide.

## Repository layout

```text
skills/<name>/                    each skill: SKILL.md, references/, scripts/
docs/<name>.md                    each skill's guide: what it does, install, use, privacy
docs/covers/                      each skill's cover for whimsical.com, and how to make one
tests/<name>/                     each skill's tests, outside the skill so they stay out of its zip
tests/repo/                       checks every skill against the conventions
.claude-plugin/marketplace.json   the Claude Code catalog: each skill's version and MCP servers
.github/workflows/                tests on every change; per tag, a release zip of every skill and a website rebuild
```

[CONTRIBUTING.md](CONTRIBUTING.md) explains how to change or add a skill, and
[CONVENTIONS.md](CONVENTIONS.md) the rules every skill follows.

## Security and privacy

The skills don't collect anything. Your agent talks to Whimsical and any other service
through their own MCP servers. [SECURITY.md](SECURITY.md) explains what the skills can
access and how to report a problem.

## License

[MIT](LICENSE), except the fonts in `docs/covers/fonts/`, which are under the
[SIL Open Font License](docs/covers/fonts/OFL-Monsical.txt).
