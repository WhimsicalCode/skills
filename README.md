# Whimsical skills

Agent skills that build [Whimsical](https://whimsical.com) boards through the
[Whimsical MCP](https://whimsical.com/learn/integrations/mcp).

| Skill | What it does |
| --- | --- |
| [App Wireframe](plugins/app-wireframe) | Turns any app into editable lo-fi wireframes: name an app to pull its screens from Mobbin, or bring your own screenshots. |

## Install

### Claude Code

Add the marketplace once, then install the skills you want:

```text
/plugin marketplace add WhimsicalCode/skills
/plugin install app-wireframe@whimsical
```

Each plugin adds its skill and the MCP servers it needs. Each skill's README covers the
rest of its setup.

### Other agents

Each skill is a folder under `plugins/<name>/skills/`. Copy it into the folder your
agent loads skills from, and add the MCP servers listed in that skill's README.

## Repository layout

```text
.claude-plugin/marketplace.json   lists every plugin
plugins/<name>/                   one plugin per skill: manifest, MCP servers, skill, tests
.github/workflows/<name>.yml      each plugin's tests, run when its folder changes
```

## License

[MIT](LICENSE)
