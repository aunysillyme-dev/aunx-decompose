#!/usr/bin/env node
// Install the Decompose skill into agent skills folders, or run its checker.
import { cpSync, existsSync, readFileSync, rmSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const skill = join(root, 'skills', 'decompose');
const { version } = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
const agents = {
  claude: ['.claude/skills', '.claude/skills'],
  codex: ['.agents/skills', '.agents/skills'],
  gemini: ['.gemini/skills', '.gemini/skills'],
  cursor: ['.cursor/skills', '.cursor/skills'],
  opencode: ['.config/opencode/skills', '.opencode/skills'],
  copilot: ['.copilot/skills', '.github/skills'],
  qwen: ['.qwen/skills', '.qwen/skills'],
};
const validAgents = [...Object.keys(agents), 'all'].join(', ');
const help = `aunx-decompose ${version}

Usage:
  npx aunx-decompose install [--agent <name>]... [--project] [--force]
      Copy the skill to each agent's user skills folder, or project skills
      folder with --project. Agents: ${validAgents}.
      Defaults to claude (~/.claude/skills/decompose or ./.claude/skills/decompose).
      Repeat --agent to select several agents; all selects all seven.
      --force replaces an existing copy at each destination.
      Existing copies are left unchanged otherwise; other installs continue.
  npx aunx-decompose check <args>
      Run the checker (Python 3.8+), for example: check --plan plan.json
  npx aunx-decompose --version | --help`;

function install(args) {
  const selected = new Set();
  let project = false;
  let force = false;
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--project') {
      project = true;
    } else if (arg === '--force') {
      force = true;
    } else if (arg === '--agent') {
      const name = args[++i];
      if (name !== 'all' && !Object.hasOwn(agents, name)) {
        console.error(`Unknown agent: ${name ?? '(missing)'}. Valid agents: ${validAgents}`);
        process.exitCode = 2;
        return;
      }
      for (const agent of name === 'all' ? Object.keys(agents) : [name]) {
        selected.add(agent);
      }
    } else {
      console.error(`Unknown install option: ${arg}\n\n${help}`);
      process.exitCode = 2;
      return;
    }
  }
  if (!selected.size) selected.add('claude');
  for (const agent of selected) {
    const dest = join(project ? process.cwd() : homedir(), agents[agent][project ? 1 : 0], 'decompose');
    if (existsSync(dest) && !force) {
      console.error(`${dest} already exists. Rerun with --force to replace it.`);
      process.exitCode = 1;
      continue;
    }
    try {
      rmSync(dest, { recursive: true, force: true });
      cpSync(skill, dest, { recursive: true, filter: (src) => !src.includes('__pycache__') });
      console.log(`Installed Decompose ${version} to ${dest}`);
    } catch (error) {
      console.error(`Could not install to ${dest}: ${error.message}`);
      process.exitCode = 1;
    }
  }
}

const [cmd, ...rest] = process.argv.slice(2);

if (!cmd || cmd === '--help' || cmd === '-h') {
  console.log(help);
} else if (cmd === '--version' || cmd === '-v') {
  console.log(version);
} else if (cmd === 'install') {
  if (rest.includes('--help') || rest.includes('-h')) {
    console.log(help);
  } else {
    install(rest);
  }
} else if (cmd === 'check') {
  const python = process.platform === 'win32' ? 'python' : 'python3';
  const run = spawnSync(python, [join(skill, 'scripts', 'decompose.py'), ...rest], { stdio: 'inherit' });
  if (run.error) {
    console.error(`Could not run ${python}: ${run.error.message}`);
    process.exitCode = 1;
  } else {
    process.exitCode = run.status ?? 1;
  }
} else {
  console.error(`Unknown command: ${cmd}\n\n${help}`);
  process.exitCode = 2;
}
