# Security

## Reporting a problem

Please report security problems privately, with **Report a vulnerability** on the
repository's [Security tab](https://github.com/WhimsicalCode/skills/security), not in a
public issue. Say which skill, what an attacker could do, and how to reproduce it. We'll
reply there.

## What the skills can access

A skill is instructions and small scripts that your agent runs with your permissions. What
it can reach depends on what you've connected and allowed:

- **MCP servers you connected.** The skills read and change Whimsical boards through the
  Whimsical MCP, with your account's access, and read from the other services each skill's
  guide lists. They create new boards rather than edit existing ones, unless you name one.
- **Files.** Scripts read the files you point them to and write working files in a folder
  named after the task, in the folder your agent was started in.
- **Network.** Scripts only reach the hosts their skill's guide names. App Wireframe, for
  example, fetches from mobbin.com and Mobbin's image host, with size limits, and never
  follows a redirect elsewhere. Scripts that use packages download them through
  [uv](https://docs.astral.sh/uv/) from PyPI the first time they run.

Nothing is collected or sent anywhere else.

## Content from outside

Skills read content you didn't write: Mobbin pages and screenshots, emails, CRM records.
The skills treat it as data to describe, never as instructions to follow. If you find
content that makes a skill do something you didn't ask for, please report it as above.
