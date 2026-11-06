# Whimsical skills

Skills that let your AI agent build [Whimsical](https://whimsical.com) boards for you,
through the [Whimsical MCP](https://whimsical.com/learn/integrations/mcp). Each one is a
standard [Agent Skills](https://agentskills.io) folder, so it works in Claude, Cursor,
Codex, GitHub Copilot, Gemini CLI and other agents that read skills.

| Skill | What it does | Try |
| --- | --- | --- |
| [App Wireframe](docs/app-wireframe.md) | Turns any app into editable lo-fi wireframes: name an app to pull its screens from Mobbin, or bring your own screenshots. [See 20 example boards](https://whimsical.com/templates/wireframes). | `Make wireframes of Airbnb` |

These skills are new, and mostly written with coding agents. If something breaks in your
setup, please [open an issue](https://github.com/WhimsicalCode/skills/issues/new/choose).

## Install

Every skill needs the Whimsical MCP, and some need another MCP server too. Each skill's
guide, linked above, lists them and covers the rest of the setup.

### Claude Code

Add the Whimsical marketplace once, then install the skills you want:

```text
/plugin marketplace add WhimsicalCode/skills
/plugin install app-wireframe@whimsical
```

Each plugin adds its skill and the MCP servers it needs. Restart Claude Code and run
`/mcp` to sign in.

### Claude apps (claude.ai and the desktop app)

1. Download the skill's zip from the
   [latest release](https://github.com/WhimsicalCode/skills/releases/latest), for example
   [`app-wireframe.zip`](https://github.com/WhimsicalCode/skills/releases/latest/download/app-wireframe.zip).
2. In Claude, open **Customize** (on claude.ai, [claude.ai/customize/skills](https://claude.ai/customize/skills)),
   click **Add**, then **Upload skill**, drop the zip and click **Upload**.
3. Still in **Customize**, under **Connectors**, add Whimsical and any other connector
   the skill's guide lists.

### Cursor, Codex, GitHub Copilot, Gemini CLI and other agents

With [Node.js](https://nodejs.org) installed, run this in a terminal and pick your agent
when asked:

```sh
npx skills add WhimsicalCode/skills --skill app-wireframe
```

It copies the skill where your agent looks for skills, using the open
[skills](https://github.com/vercel-labs/skills) installer. Without Node.js, unzip the
skill's zip from the [latest release](https://github.com/WhimsicalCode/skills/releases/latest)
into that folder yourself. Either way, then add the MCP servers the skill's guide lists,
following your agent's MCP setup guide.

## Repository layout

```text
skills/<name>/                    each skill: SKILL.md, references/, scripts/
docs/<name>.md                    each skill's guide: what it does, install, use, privacy
tests/<name>/                     each skill's tests, outside the skill so they stay out of its zip
tests/repo/                       checks every skill against the conventions
.claude-plugin/marketplace.json   the Claude Code catalog: each skill's version and MCP servers
.github/workflows/                tests on every change; a release zip of every skill per tag
```

[CONTRIBUTING.md](CONTRIBUTING.md) explains how to change or add a skill, and
[CONVENTIONS.md](CONVENTIONS.md) the rules every skill follows.

## Security and privacy

The skills don't collect anything. Your agent talks to Whimsical and any other service
through their own MCP servers. [SECURITY.md](SECURITY.md) explains what the skills can
access and how to report a problem.

## License

[MIT](LICENSE)
