// Sources are read on every build. No generated product documentation is checked in.
const page = (key, route, h1, description, sources) => ({ key, route, h1, title: `${h1} | Decompose`, description, sources });
export const pages = [
  page('landing', '/', 'Decompose', 'Break a task into the smallest units that can each be checked, and show which units can run at the same time.', ['README.md', 'package.json', 'CHANGELOG.md']),
  page('overview', '/docs/overview/', 'Overview', 'What Decompose does, when to use it and what it runs and writes.', ['README.md']),
  page('how', '/docs/how-it-works/', 'How it works', 'Clauses, units, real data edges, parallel waves, the critical path and the advisor gate.', ['README.md', 'skills/decompose/SKILL.md', 'skills/decompose/references/picking.md', 'skills/decompose/recipes.json']),
  page('install', '/docs/install/', 'Install', 'Install with npm, agent plugins or skills.sh, with user and project skill destinations.', ['README.md']),
  page('usage', '/docs/usage/', 'Usage', 'Use unit maps, step plans and the bundled slash command.', ['README.md', 'commands/decompose.md']),
  page('checks', '/docs/checks/', 'Checks and exit codes', 'Validation, write-path overlap checks and unit map and step plan exit codes.', ['README.md', 'skills/decompose/scripts/decompose.py', 'skills/decompose/scripts/unitmap.py']),
  page('compatibility', '/docs/compatibility/', 'Compatibility', 'Agent packaging, CLI-checked coverage and requirements.', ['README.md', 'package.json']),
  page('changelog', '/docs/changelog/', 'Changelog', 'The current changelog read directly from the repository.', ['CHANGELOG.md']),
];
export default pages;
