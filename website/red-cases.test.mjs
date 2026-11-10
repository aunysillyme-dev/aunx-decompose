import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, cpSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { buildSite } from './build.mjs';
import { rootDir } from './facts.mjs';

// Corruption is restricted to disposable checker fixtures, never website/dist.
const cases = [
  ['rendered version differs', 'rendered version differs from package.json', (dir) => {
    const file = join(dir, 'index.html');
    writeFileSync(file, readFileSync(file, 'utf8').replace(/data-version>v[^<]+/, 'data-version>v999.999.999'));
  }],
  ['broken internal link', 'broken internal link', dir => {
    const file = join(dir, 'index.html');
    writeFileSync(file, readFileSync(file, 'utf8').replace('href="/docs/install/"', 'href="/docs/missing/"'));
  }],
  ['missing page from pages.mjs', 'docs/usage/index.html: missing output file', dir => rmSync(join(dir, 'docs/usage/index.html'))],
  ['em dash in copy', 'em dash in site copy', dir => {
    const file = join(dir, 'index.html');
    writeFileSync(file, readFileSync(file, 'utf8').replace('Common questions', 'Common questions' + String.fromCharCode(0x2014)));
  }],
  ['default sitemap', 'sitemap.xml: forbidden in default mode', dir => writeFileSync(join(dir, 'sitemap.xml'), '<urlset/>')],
  ['default missing noindex', 'missing noindex in default mode', dir => {
    const file = join(dir, 'index.html');
    writeFileSync(file, readFileSync(file, 'utf8').replace('<meta name="robots" content="noindex">', ''));
  }],
];
const parent = mkdtempSync(join(rootDir, 'website/.red-fixtures-'));
try {
  const clean = join(parent, 'clean');
  buildSite({ outDir: clean });
  const run = dir => spawnSync(process.execPath, [join(rootDir, 'website/check.mjs'), '--dist', dir], { encoding: 'utf8' });
  for (const [name, diagnostic, corrupt] of cases) await test(name + ': RED then GREEN', () => {
    const fixture = join(parent, name.replaceAll(' ', '-'));
    cpSync(clean, fixture, { recursive: true });
    corrupt(fixture);
    const red = run(fixture);
    assert.equal(red.status, 1, red.stdout + red.stderr);
    assert.ok((red.stdout + red.stderr).includes(diagnostic), red.stdout + red.stderr);
    console.log(`RED ${name}: exit ${red.status}; ${red.stderr.trim().split('\n').filter(line => line.includes(diagnostic)).join('; ')}`);
    rmSync(fixture, { recursive: true });
    cpSync(clean, fixture, { recursive: true });
    const green = run(fixture);
    assert.equal(green.status, 0, green.stdout + green.stderr);
    console.log(`GREEN ${name}: exit ${green.status}; ${green.stdout.trim()}`);
  });
} finally { rmSync(parent, { recursive: true, force: true }); }
