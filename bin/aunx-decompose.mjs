#!/usr/bin/env node
// Install the Decompose skill into a Claude skills folder, or run its checker.
import { cpSync, existsSync, readFileSync, rmSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const skill = join(root, 'skills', 'decompose');
const { version } = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
const help = `aunx-decompose ${version}

Usage:
  npx aunx-decompose install [--project] [--force]
      Copy the skill to ~/.claude/skills/decompose, or ./.claude/skills/decompose
      with --project. --force replaces an existing copy.
  npx aunx-decompose check <args>
      Run the checker (Python 3.8+), for example: check --plan plan.json
  npx aunx-decompose --version | --help`;

const [cmd, ...rest] = process.argv.slice(2);

if (!cmd || cmd === '--help' || cmd === '-h') {
  console.log(help);
} else if (cmd === '--version' || cmd === '-v') {
  console.log(version);
} else if (cmd === 'install') {
  const base = rest.includes('--project') ? join(process.cwd(), '.claude') : join(homedir(), '.claude');
  const dest = join(base, 'skills', 'decompose');
  if (existsSync(dest) && !rest.includes('--force')) {
    console.error(`${dest} already exists. Rerun with --force to replace it.`);
    process.exitCode = 1;
  } else {
    rmSync(dest, { recursive: true, force: true });
    cpSync(skill, dest, { recursive: true, filter: (src) => !src.includes('__pycache__') });
    console.log(`Installed Decompose ${version} to ${dest}`);
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
