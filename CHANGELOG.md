# Changelog

## 0.3.0

- Multi-agent skill installs: repeat `--agent` for Claude Code, Codex, Gemini CLI, Cursor, OpenCode, Copilot CLI and Qwen Code, or use `--agent all`. User and project installs support `--force` per destination.
- Added Gemini CLI extension and slash command, Codex plugin manifest, and Cursor plugin and marketplace. The Claude Code manifest also supports Copilot CLI.
- Agent-neutral helper path guidance, matching plugin versions and npm package metadata, with the existing Claude Code, Hermes and skills.sh install paths preserved.

## 0.2.1

- Published on npm as `aunx-decompose`. `npx aunx-decompose install` copies the skill to `~/.claude/skills/decompose`, and `npx aunx-decompose check` runs the checker.
- Listed on skills.sh: `npx skills add aunysillyme-dev/aunx-skills --skill decompose`.
- The skill now works when installed on its own, outside the plugin, where `CLAUDE_PLUGIN_ROOT` is not set.
- README trailer, a CHANGELOG, and search and AI answer metadata (keywords, FAQ, llms.txt).

## 0.2.0

- Unit maps: 14 types by 3 speeds, clause coverage, false and missing edge checks, parallel waves, dispatch shapes, an advisor gate with patches, the critical path and a plan table.

## 0.1.0

- Step plans with dependency cycle and write-path overlap checks, parallel waves and reusable task recipes.
