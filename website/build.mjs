import { readFileSync, writeFileSync, mkdirSync, rmSync, copyFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname, resolve, posix } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { buildJsonLd, buildFaqJsonLd, loadSourceFacts, visibleText, section } from './facts.mjs';
import { pages } from './pages.mjs';
import { content } from './content.mjs';
import { renderProjectsPopup } from './projects-popup-render.mjs';

const origin = 'https://decompose.aunysillyme.dev';
const repository = 'https://github.com/aunysillyme-dev/aunx-decompose';
import { assets, csp, fontStylesheet, hasVideo } from './resources.mjs';
const read = (root, file) => readFileSync(join(root, file), 'utf8');
const json = (root, file) => JSON.parse(read(root, file));
const requireValue = (ok, message) => { if (!ok) throw Error(message); };
export const escape = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const slug = text => visibleText(text).toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, '').trim().replace(/\s+/g, '-') || 'section';

// The pinned project set is the one source for the header popup and the sidebar siblings.
function readSet(root) {
  const { rows } = json(root, 'website/set.json');
  requireValue(Array.isArray(rows) && rows.length > 0, 'Project set rows missing in website/set.json');
  return rows;
}

function projectsPopup(root) {
  return renderProjectsPopup({ rows: readSet(root), current: '', id: 'projects-popup', fallbackHref: 'https://aunysillyme.dev/#projects' });
}

function validatePages() {
  requireValue(pages.length === 8 && new Set(pages.map(page => page.route)).size === 8, 'Expected eight unique pages');
  for (const page of pages) requireValue(page.title && page.description && page.h1 && page.sources.length, `Incomplete page: ${page.route}`);
}

function sourceRoutes() {
  const routes = new Map();
  for (const page of pages.filter(page => page.route !== '/')) {
    for (const source of page.sources) if (!routes.has(source)) routes.set(source, page.route);
  }
  return routes;
}

export function rewriteUrl(href, source, { image = false, routes = sourceRoutes() } = {}) {
  if (!href || /[\u0000-\u0020\u007f\\]/.test(href)) return '';
  if (image) {
    const local = href.startsWith('/assets/') ? href.slice(8) : posix.normalize(posix.join(posix.dirname(source), href)).replace(/^website\/assets\//, '');
    return assets.includes(local) && /\.(?:png|svg)$/.test(local) ? `/assets/${local}` : '';
  }
  if (href.startsWith('#')) return href;
  if (/^https?:\/\//i.test(href)) return href;
  if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(href)) return '';
  const [file, fragment] = href.split('#');
  const normalized = posix.normalize(file.startsWith('/') ? file.slice(1) : posix.join(posix.dirname(source), file));
  if (normalized === '..' || normalized.startsWith('../')) return '';
  const suffix = fragment ? `#${fragment}` : '';
  return routes.has(normalized) ? `${routes.get(normalized)}${suffix}` : `${repository}/blob/main/${normalized}${suffix}`;
}

function uniqueId(text, ids) {
  const base = slug(text);
  let id = base, count = 0;
  while (ids.has(id)) id = `${base}-${++count}`;
  ids.add(id);
  return id;
}

// Source HTML is data. Only tags constructed by this renderer reach the page.
export function renderMarkdown(markdown, { source = 'README.md', ids = new Set(), routes = sourceRoutes() } = {}) {
  const references = new Map();
  markdown = markdown.replace(/^---\n[^]*?\n---\n/, '').replace(/<!--[^]*?-->/g, ' ');
  markdown = markdown.replace(/^\[([^\]]+)\]:\s*(\S+).*$/gm, (_, label, href) => { references.set(label.toLowerCase(), href); return ''; });
  function inline(value, tokens = []) {
    const save = html => { tokens.push(html); return `\u0000${tokens.length - 1}\u0000`; };
    value = value.replace(/`([^`]+)`/g, (_, code) => save(`<code>${escape(code)}</code>`));
    value = value.replace(/<(script|style|iframe|object|svg)\b[^>]*>[^]*?<\/\1\s*>/gi, ' ').replace(/<\/?[a-z][^>]*>/gi, ' ');
    value = value.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, href) => {
      const src = rewriteUrl(href, source, { image: true, routes });
      return save(src ? `<img src="${escape(src)}" alt="${escape(alt)}" loading="lazy">` : '');
    });
    value = value.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
      const url = rewriteUrl(href, source, { routes });
      const rendered = inline(label, tokens);
      return save(rendered.trim() && url ? `<a href="${escape(url)}">${rendered}</a>` : rendered);
    });
    value = value.replace(/\[([^\]]+)\](?:\[([^\]]*)\])?/g, (whole, label, reference) => {
      const href = references.get((reference || label).toLowerCase());
      if (!href) return whole;
      const url = rewriteUrl(href, source, { routes });
      const rendered = inline(label, tokens);
      return save(rendered.trim() && url ? `<a href="${escape(url)}">${rendered}</a>` : rendered);
    });
    value = value.replace(/https?:\/\/[^\s<>"'\u0000]+/g, whole => {
      const href = whole.replace(/[.,;]+$/, '');
      return save(`<a href="${escape(href)}">${escape(href)}</a>`) + whole.slice(href.length);
    });
    value = escape(value).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
    return value.replace(/\u0000(\d+)\u0000/g, (_, index) => tokens[Number(index)]);
  }
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  for (let index = 0; index < lines.length;) {
    const line = lines[index];
    if (!line.trim()) { index++; continue; }
    if (/^\s*```/.test(line)) {
      const code = [];
      index++;
      while (index < lines.length && !/^\s*```/.test(lines[index])) code.push(lines[index++]);
      index++;
      blocks.push(`<pre><code>${escape(code.join('\n'))}</code></pre>`);
      continue;
    }
    // Drop active raw HTML blocks before joining their lines into paragraphs.
    if (/^\s*<(script|style|iframe|object|svg)\b/i.test(line)) {
      const tag = line.match(/<(\w+)/)[1];
      const raw = [];
      do { raw.push(lines[index]); if (new RegExp(`</${tag}\\s*>`, 'i').test(lines[index++])) break; } while (index < lines.length);
      const safe = inline(raw.join('\n'));
      if (safe.trim()) blocks.push(`<p>${safe}</p>`);
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const depth = Math.max(2, heading[1].length);
      const text = inline(heading[2]);
      blocks.push(`<h${depth} id="${uniqueId(text, ids)}">${text}</h${depth}>`);
      index++; continue;
    }
    if (/^\|/.test(line) && /^\|\s*:?-{3}/.test(lines[index + 1] || '')) {
      const cells = value => value.trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|/).map(cell => inline(cell.trim().replace(/\\\|/g, '|')));
      const head = cells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && /^\|/.test(lines[index])) rows.push(cells(lines[index++]));
      blocks.push(`<div class="table-scroll"><table><thead><tr>${head.map(cell => `<th scope="col">${cell}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
      continue;
    }
    if (/^\s*(?:[-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line), items = [];
      const pattern = ordered ? /^\s*\d+\.\s+/ : /^\s*[-*]\s+/;
      while (index < lines.length && pattern.test(lines[index])) items.push(`<li>${inline(lines[index++].replace(pattern, ''))}</li>`);
      blocks.push(`<${ordered ? 'ol' : 'ul'}>${items.join('')}</${ordered ? 'ol' : 'ul'}>`);
      continue;
    }
    if (/^>/.test(line)) {
      const quote = [];
      while (index < lines.length && /^>/.test(lines[index])) quote.push(lines[index++].replace(/^>\s?/, ''));
      blocks.push(`<blockquote><p>${inline(quote.join('\n'))}</p></blockquote>`);
      continue;
    }
    if (/^\s*(?:---+|\*\*\*+)\s*$/.test(line)) { blocks.push('<hr>'); index++; continue; }
    const paragraph = [lines[index++]];
    while (index < lines.length && lines[index].trim() && !/^(?:#{1,6}\s|\s*```|\||>|\s*[-*]\s|\s*\d+\.\s|\s*<(?:script|style|iframe|object|svg)\b)/i.test(lines[index])) paragraph.push(lines[index++]);
    const rendered = inline(paragraph.join('\n'));
    if (rendered.trim()) blocks.push(`<p>${rendered}</p>`);
  }
  return blocks.join('\n');
}

function cardTrace() {
  return '<svg class="card-trace" aria-hidden="true" focusable="false"><rect class="ray-tail" x=".5" y=".5" pathLength="100"/><rect class="ray-mid" x=".5" y=".5" pathLength="100"/><rect class="ray-tip" x=".5" y=".5" pathLength="100"/></svg>';
}

function docsBody(root, page, facts) {
  let markdown;
  const readme = facts.readme;
  if (page.key === 'overview') markdown = facts.lead + '\n\n' + ['When to use it', 'What it runs and writes'].map(h => section(readme, h)).join('\n\n');
  else if (page.key === 'how') markdown = facts.method + '\n\n' + section(readme, 'Unit map example') + '\n\n' + section(facts.skill, 'Unit maps: the full method');
  else if (page.key === 'install') markdown = section(readme, 'Install');
  else if (page.key === 'usage') markdown = ['Unit map example', 'Step plan example'].map(h => section(readme, h)).join('\n\n');
  else if (page.key === 'checks') markdown = [section(readme, 'Unit map example').slice(section(readme, 'Unit map example').indexOf('Unit map exit codes:')), section(readme, 'Step plan example').slice(section(readme, 'Step plan example').indexOf('Step plan exit codes:')), section(readme, 'Step kinds')].join('\n\n');
  else if (page.key === 'compatibility') markdown = facts.compatibility + '\n\nCursor, OpenCode, Qwen Code and Hermes are not live-tested.\n\n' + facts.lead + '\n\n' + section(readme, 'Install');
  else markdown = facts.changelog;
  const ids = new Set(['main', 'page-title']);
  const source = page.key === 'changelog' ? 'CHANGELOG.md' : 'README.md';
  let body = `<p class="source-note">From <a href="${repository}/blob/main/${source}">${source}</a></p>` + renderMarkdown(markdown, { source, ids });
  if (page.key === 'how') body += `<h2 id="picking">Model and machine picks</h2><p>The helper never picks or calls a model or a machine. Picking is a written method for the agent.</p><p><a href="${repository}/blob/main/skills/decompose/references/picking.md">Read the picking method</a></p><h2 id="thresholds">Current recipe defaults</h2><pre><code>${escape(JSON.stringify(facts.recipes.plan_defaults, null, 2))}</code></pre>`;
  if (page.key === 'usage') body += `<h2 id="slash-command">Slash command wrapper</h2>${renderMarkdown(facts.command, { source: 'commands/decompose.md', ids })}`;
  return `<article class="markdown">${body}</article>`;
}

function landingBody(root, facts) {
  const heading = (title, id, label, body, extra = '') => `<section class="content ${extra}" id="${id}"><div class="section-title"><h2>${escape(title)}</h2><span>${escape(label)}</span></div>${body}</section>`;
  const graphic = `<div class="routing card">${cardTrace()}<div class="routing-head"><span>ONE TASK, CHECKABLE UNITS</span><span>THE PLANNING METHOD</span></div><div class="task-tabs" role="group" aria-label="Planning stages">${[['clauses','Clauses','Split the ask into numbered clauses.'],['units','Units','Break the job into the smallest units, each with its own inputs, outputs and verifier.'],['waves','Waves','Draw only real data edges. Build parallel waves.'],['check','Check','Print one plan table with the waves, the critical path and clause coverage.']].map(([key, title, caption], i) => `<button type="button" data-task="${key}" data-caption="${caption}" aria-pressed="${i === 0}">${title}</button>`).join('')}</div><div class="task" id="task-text" aria-live="polite">Split the ask into numbered clauses.</div><div class="stem"></div><div class="route-core selected" data-role="clauses">THE ASK → NUMBERED CLAUSES</div><div class="split"></div><div class="route-options"><div data-role="units"><b>Units</b>Inputs, outputs, verifier</div><div data-role="waves"><b>Waves</b>Real data edges</div><div data-role="check"><b>Check</b>Critical path + coverage</div></div><p class="route-foot">Your agent writes the plan.<br>A Python helper that uses only the standard library checks it.</p></div>`;
  const faq = facts.faq.map(row => `<details><summary>${escape(row.question)}</summary>${renderMarkdown(row.answerMarkdown, { source: 'README.md' })}</details>`).join('');
  const fallbackTrailer = `<div class="trailer-media" data-gif-trailer><img src="/assets/trailer-poster.png" data-poster alt="Decompose: the ask, clauses, units, waves and plan checks" width="1280" height="720"><img data-animation data-src="/assets/trailer.gif" hidden alt="A silent 14-second tour of Decompose" width="1280" height="720"></div><noscript><p><a href="/assets/trailer.gif">Play the GIF trailer</a></p></noscript><div class="trailer-caption"><p class="note">A 14-second tour of Decompose. Silent GIF trailer.</p><button type="button" class="trailer-toggle" aria-label="Play trailer" aria-pressed="false"><svg class="icon-pause" viewBox="0 0 12 12" aria-hidden="true" focusable="false"><rect x="2" y="1.5" width="3" height="9"/><rect x="7" y="1.5" width="3" height="9"/></svg><svg class="icon-play" viewBox="0 0 12 12" aria-hidden="true" focusable="false"><path d="M3 1.5v9l7.5-4.5z"/></svg><span class="sr-only" data-button-label>Play trailer</span></button></div>`;
  const trailer = hasVideo ? `<video muted loop playsinline preload="none" width="960" height="540" poster="/assets/trailer-poster.png" aria-label="A silent 14-second tour of Decompose"><source src="/assets/trailer.webm" type="video/webm"><source src="/assets/trailer.mp4" type="video/mp4"><a href="/assets/trailer.mp4">Watch the trailer</a></video>${fallbackTrailer.slice(fallbackTrailer.indexOf('<div class="trailer-caption">')).replace('Silent GIF trailer.', 'Silent video.')}` : fallbackTrailer;
  return `<div class="crumb"><a href="https://aunysillyme.dev">Home</a><span>/</span><b>Decompose</b></div>
<section class="hero" id="overview"><div><p class="eyebrow">${escape(content.eyebrow)}</p><h1>${escape(content.headline)}<br><em>${escape(content.headlineAccent)}</em></h1><p class="lede">${escape(facts.lead)}</p><div class="install card">${cardTrace()}<span class="dollar" aria-hidden="true">$</span><code id="install-command">${escape(content.install.command)}</code><button class="copy" type="button" data-copy="install-command" aria-label="Copy install command"><span data-button-label>⧉</span></button></div><div class="hero-actions"><a class="primary" href="#quickstart">Get started ↓</a><a href="${repository}">Explore the source ↗</a></div></div>${graphic}</section>
<div class="trust"><span>Python 3.8+</span><span>Standard library</span><span>No API keys</span><span>MIT licensed</span></div>
${heading('What this does', 'trailer', 'WATCH THE TRAILER', trailer, 'trailer')}
${heading('From the ask to a checked plan.', 'how-it-works', 'HOW IT WORKS', `<div class="markdown">${renderMarkdown(facts.method)}</div><p><a href="/docs/how-it-works/">Clauses, units, waves and the advisor gate ↗</a></p>`)}
${heading('Install for your agent.', 'quickstart', 'GETTING STARTED', `<div class="docs-grid"><div class="markdown">${renderMarkdown(section(facts.readme, 'Install').split('### Skill only')[0])}</div><div><div class="code card">${cardTrace()}<pre><code>npx aunx-decompose install\n\nnpx aunx-decompose install --agent codex\n\nnpx aunx-decompose install --agent all</code></pre></div><p class="note">Skill-only installs default to Claude Code. Repeat --agent to select several.</p><a href="/docs/install/">All install options and skills.sh ↗</a></div></div>`)}
${heading('Go a little deeper.', 'reference', 'DOCUMENTATION', `<div class="docs-links">${pages.filter(page => page.route !== '/').map(page => `<a class="doc-link card" href="${page.route}">${cardTrace()}${page.h1} ↗<span>${page.description}</span></a>`).join('')}</div>`)}
${heading('Which agents does it support?', 'compatibility', 'FROM THE README', `<div class="markdown">${renderMarkdown(facts.compatibility)}<p>Cursor, OpenCode, Qwen Code and Hermes are not live-tested.</p></div>`)}
${heading('Common questions', 'questions', 'FROM THE README', `<div class="markdown faq">${faq}</div>`)}
${heading('Fresh from the repo.', 'releases', 'RELEASE NOTES', `<div class="release"><strong data-release-version>v${escape(facts.version)}</strong><div class="markdown">${renderMarkdown(facts.changelog.split(/\n## /)[1]?.replace(/^[^\n]*\n/, '') || '')}</div></div><p><a href="/docs/changelog/">Full changelog ↗</a></p>`)}`;
}

function navigation(page) {
  if (page.route === '/') return content.nav.map(link => `<a href="${escape(link.href)}"${link.href === '#overview' ? ' class="active" aria-current="location"' : ''}>${escape(link.label)}</a>`).join('\n');
  return pages.filter(item => item.route !== '/').map(item => `<a href="${item.route}"${item.route === page.route ? ' class="active" aria-current="page"' : ''}>${escape(item.h1)}</a>`).join('\n');
}

function sidebar(root, page) {
  const siblings = readSet(root).filter(row => row.name !== content.brand);
  if (page.route !== '/') return `<p class="side-label">DOCUMENTATION</p><nav class="side-links" aria-label="Documentation">${navigation(page)}</nav><div class="side-bottom">Questions or feedback?<a class="issue-button" href="${repository}/issues/new/choose" target="_blank" rel="noopener noreferrer">File an issue ↗</a></div>`;
  return `<p class="side-label">${page.route === '/' ? escape(content.brand.toUpperCase()) : content.docsLabel}</p><nav class="side-links" aria-label="Documentation">${navigation(page)}</nav><p class="side-label">THE REST OF THE SET</p><nav class="side-links" aria-label="Related repositories">${siblings.map(row => `<a href="${escape(row.url)}" target="_blank" rel="noopener noreferrer">${escape(row.name)} ↗</a>`).join('')}<\/nav><div class="side-bottom"><div>Questions or feedback?</div><a class="issue-button" href="${repository}/issues/new/choose" target="_blank" rel="noopener noreferrer" aria-label="File an issue for ${escape(content.brand)} on GitHub">File an issue ↗</a><span>Open source · MIT license</span></div>`;
}

function head(page, facts, live, notFound = false) {
  const url = `${origin}${page.route}`;
  const blocks = [];
  if (page.route === '/' && !notFound) blocks.push(buildJsonLd(facts, { live }), buildFaqJsonLd(facts));
  else if (!notFound) blocks.push({ '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: [
    { '@type': 'ListItem', position: 1, name: content.brand, item: `${origin}/` },
    { '@type': 'ListItem', position: 2, name: 'Documentation', item: url },
  ] });
  return `<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="is-agentic-site-type" content="app">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<title>${escape(page.title)}</title>
<meta name="description" content="${escape(page.description)}">
<link rel="canonical" href="${url}">
${!live || notFound ? '<meta name="robots" content="noindex">' : `<link rel="describedby" href="${origin}/llms.txt">
<link rel="alternate" type="text/markdown" href="${url}index.md">
<meta property="og:type" content="website">
<meta property="og:title" content="${escape(page.title)}">
<meta property="og:description" content="${escape(page.description)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${origin}/assets/social-preview.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="${escape(content.socialAlt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escape(page.title)}">
<meta name="twitter:description" content="${escape(page.description)}">
<meta name="twitter:image" content="${origin}/assets/social-preview.png">
<meta name="twitter:image:alt" content="${escape(content.socialAlt)}">`}
<link rel="icon" href="/assets/avatar.png"><link rel="apple-touch-icon" href="/assets/avatar.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="${fontStylesheet}" rel="stylesheet">
<link rel="stylesheet" href="/assets/site.css">
<link rel="stylesheet" href="/assets/projects-popup.css">
<script type="module" src="/assets/site.js"></script>
<script defer src="/assets/projects-popup.js"></script>
${blocks.map(block => `<script type="application/ld+json">${JSON.stringify(block, null, 2).replace(/</g, '\\u003c')}</script>`).join('\n')}`;
}

function footer(commit, page) {
  if (page.route !== '/') return `<footer class="bottom"><a href="/">← Back to ${escape(content.brand)}</a><a href="${repository}/issues/new/choose" target="_blank" rel="noopener noreferrer">File an issue ↗</a></footer>`;
  return `<p id="copy-status" class="sr-only" role="status" data-success="${escape(content.install.copySuccess)}" data-fallback="${escape(content.install.copyFallback)}"></p><footer class="bottom"><span>Built by <a href="https://aunysillyme.dev/">AunySillyMe</a> · Checkable units. Parallel waves. MIT licensed.</span><a href="${repository}">${escape(content.footer.repository)} ↗</a><span>${escape(content.footer.source)} <a href="${repository}/commit/${commit}">${commit.slice(0, 7)}</a></span></footer>`;
}

function documentBody(page, body, commit, buildTime) {
  const firstSource = body.match(/<p class="source-note">[^]*?<\/p>/)?.[0] || '';
  body = body.replace(firstSource, '');
  const provenance = firstSource.replace('/blob/main/', `/blob/${commit}/`).replace('</p>', ` · <a href="${repository}/tree/${commit}">${commit.slice(0, 7)}</a> · Built ${escape(buildTime.slice(0, 10))}</p>`);
  return `<nav class="crumb" aria-label="${escape(content.breadcrumbs.label)}"><a href="/">${escape(content.brand)}</a><span aria-hidden="true">/</span><span>Documentation</span></nav>${provenance}<article class="markdown"><h1 id="page-title">${escape(page.h1)}</h1></article>${body}`;
}

function template(root, page, body, facts, live, commit, notFound = false) {
  const file = page.route === '/' && !notFound ? 'landing.template.html' : 'doc.template.html';
  const header = page.route === '/' ? `<a class="skip" href="#main">${escape(content.skip)}</a><header class="top"><a class="brand" href="https://aunysillyme.dev/" target="_blank" rel="noopener noreferrer"><img src="/assets/avatar.png" alt="AunySillyMe"><span>AunySillyMe.dev</span><span class="slash">/</span><b>${escape(content.brand)}</b></a><nav class="topnav" aria-label="${escape(content.projectLinks)}"><span class="pill"><i class="dot"></i><span data-version>v${escape(facts.version)}</span></span>${projectsPopup(root)}<a href="${repository}" target="_blank" rel="noopener noreferrer">GitHub ↗</a><a href="${facts.npm}" target="_blank" rel="noopener noreferrer">npm ↗</a></nav></header>` : `<a class="skip" href="#main">${escape(content.skip)}</a><header class="top"><a class="brand" href="/"><img src="/assets/avatar.png" alt="AunySillyMe"><span>${escape(content.brand)}</span></a><nav class="topnav" aria-label="Project links"><a href="/">Home</a>${projectsPopup(root)}<a href="${repository}" target="_blank" rel="noopener noreferrer">GitHub ↗</a><a href="${facts.npm}" target="_blank" rel="noopener noreferrer">npm ↗</a></nav></header>`;
  const mobileNav = `<details class="mobile-nav"><summary>${escape(page.route === '/' ? content.onThisPage : 'Documentation')}</summary><nav aria-label="Mobile documentation">${navigation(page)}</nav></details>`;
  const values = { head: head(page, facts, live, notFound), header, sidebar: sidebar(root, page), mobileNav, body, footer: footer(commit, page) };
  return read(root, `website/${file}`).replace(/\{\{(\w+)\}\}/g, (_, key) => {
    requireValue(Object.hasOwn(values, key), `Unknown template slot: ${key}`);
    return values[key];
  }).replace(/<a\b([^>]*?)href="(https?:[^"]+)"([^>]*)>/g, (_, before, href, after) => `<a${before}href="${href}"${after.replace(/\s+(?:target|rel)="[^"]*"/g, '')} target="_blank" rel="noopener noreferrer">`);
}

function validateRendered(documents) {
  for (const { page, html } of documents) {
    requireValue((html.match(/<h1\b/g) || []).length === 1, `Expected one H1: ${page.route}`);
    const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
    requireValue(ids.length === new Set(ids).size, `Duplicate anchor: ${page.route}`);
  }
}

function markdownTwin(html, page) {
  let body = html.match(/<main\b[^>]*>([^]*?)<\/main>/)?.[1] || '';
  body = body.replace(/<details class="mobile-nav">[^]*?<\/details>/g, '').replace(/<footer\b[^>]*>[^]*?<\/footer>/g, '').replace(/<nav\b[^>]*>[^]*?<\/nav>/g, '');
  const codeBlocks = [];
  const saveCode = code => { codeBlocks.push(code); return `\u0000CODE${codeBlocks.length - 1}\u0000`; };
  body = body.replace(/<h([1-6])\b[^>]*>([^]*?)<\/h\1>/g, (_, depth, text) => `\n\n${'#'.repeat(Number(depth))} ${visibleText(text)}\n\n`)
    .replace(/<a href="([^"]+)"[^>]*>([^]*?)<\/a>/g, (_, href, text) => `[${visibleText(text)}](${href.startsWith('/') ? origin : ''}${href.replace(/&amp;/g, '&')})`)
    .replace(/<pre><code>([^]*?)<\/code><\/pre>/g, (_, code) => saveCode(`\n\n\`\`\`\n${decode(code)}\n\`\`\`\n\n`))
    .replace(/<code>([^]*?)<\/code>/g, (_, code) => saveCode(`\`${decode(code)}\``))
    .replace(/<\/(?:p|div|section|article|details|tr|li|figure|summary)>/g, '\n\n').replace(/<\/(?:th|td)>/g, ' | ')
    .replace(/<[^>]+>/g, ' ');
  const markdown = decode(body).replace(/</g, '&lt;').replace(/\n[ \t]+/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  // Restore code placeholders with literal delimiter searches; code contents are
  // inserted only after all HTML/entity processing has finished.
  const delimiter = '\u0000';
  let restored = '', cursor = 0;
  while (cursor < markdown.length) {
    const start = markdown.indexOf(delimiter, cursor);
    if (start < 0) break;
    const end = markdown.indexOf(delimiter, start + 1);
    if (end < 0) break;
    const token = markdown.slice(start + 1, end).match(/^CODE(\d+)$/);
    if (token) {
      restored += markdown.slice(cursor, start) + codeBlocks[Number(token[1])];
      cursor = end + 1;
    } else {
      restored += markdown.slice(cursor, start + 1);
      cursor = start + 1;
    }
  }
  return `Canonical: ${origin}${page.route}\n\n${restored + markdown.slice(cursor)}\n`;
}

function decode(text) {
  return text.replace(/&(?:amp|lt|gt|quot|#39);/g, entity => ({ '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" })[entity]);
}

export function buildSite({ root = fileURLToPath(new URL('..', import.meta.url)), outDir = join(root, 'website/dist'), live = false, commit, buildTime = new Date().toISOString() } = {}) {
  // Check all inputs and render in memory before replacing the output directory.
  requireValue(Number(process.versions.node.split('.')[0]) >= 22, 'Website build requires Node >=22');
  const facts = loadSourceFacts(root);
  validatePages(facts);
  for (const page of pages) for (const source of page.sources) requireValue(existsSync(join(root, source)), `Missing page source: ${source}`);
  commit ||= process.env.VERCEL_GIT_COMMIT_SHA || execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  requireValue(/^[a-f0-9]{40}$/i.test(commit), 'Expected a full source commit SHA');
  const documents = pages.map(page => ({ page, html: template(root, page, page.route === '/' ? landingBody(root, facts) : documentBody(page, docsBody(root, page, facts), commit, buildTime), facts, live, commit) }));
  validateRendered(documents, facts);
  for (const asset of assets) requireValue(existsSync(join(root, 'website/assets', asset)), `${live ? 'Live build' : 'Preview build'} asset missing: website/assets/${asset}. Supply the local asset before building.`);
  const output = resolve(outDir);
  requireValue(output !== resolve(root) && output !== resolve(root, 'website') && !resolve(root).startsWith(`${output}/`), 'Output must be a separate build directory');
  rmSync(output, { recursive: true, force: true });
  const write = (file, value) => { mkdirSync(dirname(join(output, file)), { recursive: true }); writeFileSync(join(output, file), value); };
  for (const { page, html } of documents) write(`${page.route.slice(1)}index.html`, html);
  const missing = { route: '/404.html', title: content.notFound.title, description: content.notFound.text, h1: content.notFound.title };
  write('404.html', template(root, missing, `<h1>${escape(missing.h1)}</h1><p>${escape(missing.description)}</p><a href="/">${escape(content.notFound.link)}</a>`, facts, false, commit, true));
  mkdirSync(join(output, 'assets'), { recursive: true });
  for (const asset of assets) copyFileSync(asset === 'trailer.gif' ? join(root, 'docs/aunx-decompose-trailer.gif') : join(root, 'website/assets', asset), join(output, 'assets', asset));
  write('robots.txt', live ? `User-agent: *\nAllow: /\nSitemap: ${origin}/sitemap.xml\n` : 'User-agent: *\nDisallow: /\n');
  if (live) {
    write('sitemap.xml', `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${pages.map(page => `  <url><loc>${origin}${page.route}</loc></url>`).join('\n')}\n</urlset>\n`);
    const twins = documents.map(({ page, html }) => ({ page, markdown: markdownTwin(html, page) }));
    for (const { page, markdown } of twins) write(`${page.route.slice(1)}index.md`, markdown);
    write('llms.txt', `# ${facts.name}\n\n> ${facts.lead}\n\n${content.discovery.install} \`${content.install.command}\`\n\n## ${content.discovery.pages}\n\n${pages.map(page => `- [${page.h1}](${origin}${page.route}): ${page.description}`).join('\n')}\n\n## ${content.discovery.source}\n\n- [${content.discovery.readme}](${repository}/blob/main/README.md)\n- [${content.discovery.npm}](${facts.npm})\n`);
    write('llms-full.txt', twins.map(twin => twin.markdown).join('\n---\n\n'));
  }
  write('build-info.json', JSON.stringify({ commit, buildTime, packageVersion: facts.version, mode: live ? 'live' : 'default', pageCount: pages.length }, null, 2) + '\n');
  function count(directory) { return readdirSync(directory, { withFileTypes: true }).reduce((total, entry) => total + (entry.isDirectory() ? count(join(directory, entry.name)) : 1), 0); }
  return { pages: documents, files: count(output), outDir: output };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2);
    requireValue(args.length <= 1 && args.every(arg => arg === '--live'), 'Usage: node website/build.mjs [--live]');
    const result = buildSite({ live: args.includes('--live') });
    console.log(`Built ${result.pages.length} pages and ${result.files} files (${args.includes('--live') ? 'live' : 'default'}).`);
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
