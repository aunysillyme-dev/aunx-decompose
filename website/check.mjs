import { readFileSync, readdirSync, existsSync, lstatSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pages } from './pages.mjs';
import { loadSourceFacts, rootDir, visibleText } from './facts.mjs';
import { assets, csp, fontStylesheet } from './resources.mjs';
const origin = 'https://decompose.aunysillyme.dev';
const pageFile = route => `${route.slice(1)}index.html`;
const twinFile = route => `${route.slice(1)}index.md`;
const decode = text => text.replace(/&(?:amp|lt|gt|quot|apos|#\d+|#x[\da-f]+);/gi, entity => {
  const named = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&apos;': "'" };
  if (named[entity]) return named[entity];
  const number = entity[2].toLowerCase() === 'x' ? parseInt(entity.slice(3), 16) : Number(entity.slice(2, -1));
  return number > 0 && number <= 0x10ffff ? String.fromCodePoint(number) : entity;
});
const text = value => decode(visibleText(value));
// Read tags once so quoted attributes and script text keep their boundaries.
export function parseHtml(html) {
  const nodes = [], stack = [];
  const pattern = /<!--[\s\S]*?-->|<![^>]*>|<\/?[a-z][a-z\d:-]*\b(?:[^>"']|"[^"]*"|'[^']*')*>/gi;
  for (let match; (match = pattern.exec(html));) {
    const tag = match[0];
    if (/^<!/.test(tag)) continue;
    const name = tag.match(/^<\/?([\w:-]+)/)[1].toLowerCase();
    if (tag.startsWith('</')) {
      const index = stack.findLastIndex(node => node.name === name);
      if (index >= 0) {
        for (const node of stack.splice(index)) { node.end = match.index; node.inner = html.slice(node.start, match.index); }
      }
      continue;
    }
    const attrs = {};
    const rest = tag.replace(/^<[\w:-]+/, '').slice(0, -1);
    for (const attr of rest.matchAll(/([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
      attrs[attr[1].toLowerCase()] = decode(attr[2] ?? attr[3] ?? attr[4] ?? '');
    }
    const node = { name, attrs, offset: match.index, start: pattern.lastIndex, end: pattern.lastIndex, inner: '', parent: stack.at(-1) };
    nodes.push(node);
    if (['script', 'style', 'textarea', 'title'].includes(name)) {
      const close = new RegExp(`</${name}\\s*>`, 'gi');
      close.lastIndex = pattern.lastIndex;
      const end = close.exec(html);
      node.end = end?.index ?? html.length;
      node.inner = html.slice(node.start, node.end);
      pattern.lastIndex = end ? close.lastIndex : html.length;
    } else if (!/\/\s*>$/.test(tag) && !['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'].includes(name)) stack.push(node);
  }
  return nodes;
}

function filesAt(root, prefix = '') {
  return readdirSync(join(root, prefix), { withFileTypes: true }).flatMap(entry => {
    const file = prefix + entry.name;
    return entry.isDirectory() ? filesAt(root, file + '/') : [file];
  }).sort();
}

export function expectedFiles(live = false) {
  return [...pages.map(page => pageFile(page.route)), '404.html', 'robots.txt', 'build-info.json',
    ...assets.map(asset => `assets/${asset}`),
    ...(live ? ['sitemap.xml', 'llms.txt', 'llms-full.txt', ...pages.map(page => twinFile(page.route))] : []),
  ].sort();
}

export function checkSite({ root = rootDir, dist = join(root, 'website/dist'), live = false } = {}) {
  const failures = [];
  const check = (ok, file, message) => { if (!ok) failures.push(`${file}: ${message}`); };
  const facts = loadSourceFacts(root);
  const all = filesAt(dist);
  const expected = expectedFiles(live);
  for (const file of expected) check(all.includes(file), file, 'missing output file');
  for (const file of all) check(expected.includes(file), file, 'unexpected output file');
  const documents = new Map();
  for (const file of all) {
    check(!lstatSync(join(dist, file)).isSymbolicLink(), file, 'symlink in output');
    if (!/\.(html|css|js|svg|json|txt|xml|md)$/.test(file)) continue;
    const value = readFileSync(join(dist, file), 'utf8');
    check(!decode(value).includes(String.fromCharCode(0x2014)), file, 'em dash in site copy');
    if (file.endsWith('.html')) documents.set(file, { html: value, nodes: parseHtml(value) });
  }
  const link = (file, href) => {
    let url;
    try { url = new URL(href, origin + '/' + file); } catch { check(false, file, `invalid URL: ${href}`); return; }
    if (url.origin !== origin) return;
    let target;
    try { target = decodeURIComponent(url.pathname).slice(1); } catch { check(false, file, 'invalid URL encoding'); return; }
    if (!target || target.endsWith('/')) target += 'index.html';
    check(all.includes(target), file, `broken internal link: ${href}`);
    if (url.hash && documents.has(target)) check(documents.get(target).nodes.some(node => node.attrs.id === decodeURIComponent(url.hash.slice(1))), file, `broken internal anchor: ${href}`);
  };
  for (const [file, { html, nodes }] of documents) {
    const route = file === '404.html' ? '/404.html' : '/' + file.replace(/index\.html$/, '');
    const tags = name => nodes.filter(node => node.name === name);
    const meta = name => tags('meta').filter(node => (node.attrs.name || node.attrs.property) === name);
    check(tags('h1').length === 1, file, 'expected one H1');
    check(tags('title').length === 1 && text(tags('title')[0].inner).length <= 60, file, 'expected title of at most 60 characters');
    check(meta('description').length === 1 && meta('description')[0].attrs.content.length <= 160, file, 'expected description of at most 160 characters');
    const ids = nodes.filter(node => 'id' in node.attrs).map(node => node.attrs.id);
    check(ids.length === new Set(ids).size, file, 'duplicate id');
    check(nodes.some(node => node.name === 'a' && node.attrs.class === 'skip' && node.attrs.href === '#main'), file, 'missing skip link');
    check(tags('meta').some(node => node.attrs['http-equiv'] === 'Content-Security-Policy' && node.attrs.content === csp), file, 'wrong CSP');
    check(tags('link').some(node => node.attrs.rel === 'canonical' && node.attrs.href === origin + route), file, 'wrong canonical');
    const noindex = meta('robots').some(node => /\bnoindex\b/.test(node.attrs.content));
    check(!live || file === '404.html' ? noindex : !noindex, file, !live ? 'missing noindex in default mode' : 'wrong indexing mode');
    if (!live) {
      check(!html.includes('"sameAs"'), file, 'sameAs in default mode');
      check(meta('og:image').length === 0 && meta('twitter:image').length === 0, file, 'social image in default mode');
      check(!tags('link').some(node => node.attrs.type === 'text/markdown'), file, 'Markdown twin in default mode');
    } else if (file !== '404.html') {
      check(meta('og:image')[0]?.attrs.content === origin + '/assets/social-preview.png', file, 'missing live social thumbnail');
      check(tags('link').some(node => node.attrs.type === 'text/markdown' && node.attrs.href === origin + route + 'index.md'), file, 'missing Markdown alternate');
    }
    for (const node of nodes) {
      for (const attr of ['href', 'src', 'poster', 'data-src', 'xlink:href']) {
        if (!(attr in node.attrs)) continue;
        const value = node.attrs[attr];
        link(file, value);
        if (/^https?:/.test(value)) {
          const external = new URL(value).origin !== origin;
          if (node.name === 'a' && external) check(node.attrs.target === '_blank' && /\bnoopener\b/.test(node.attrs.rel || '') && /\bnoreferrer\b/.test(node.attrs.rel || ''), file, `unsafe external link: ${value}`);
          else if (external) check(node.name === 'link' && (value === fontStylesheet || ['https://fonts.googleapis.com', 'https://fonts.gstatic.com'].includes(value)), file, `unexpected external resource: ${value}`);
        }
        check(!/^javascript:|^data:|^\/\//i.test(value), file, 'unsafe URL scheme');
      }
      check(!Object.keys(node.attrs).some(name => /^on/i.test(name)), file, 'inline event handler');
      if (node.name === 'script') {
        check(node.attrs.src || node.attrs.type === 'application/ld+json', file, 'inline executable script');
        if (node.attrs.type === 'application/ld+json') { try { JSON.parse(node.inner); } catch { check(false, file, 'invalid JSON-LD'); } }
      }
    }
    const page = pages.find(page => pageFile(page.route) === file);
    if (page) check(tags('aside').some(side => parseHtml(side.inner).some(node => node.name === 'a' && node.attrs['aria-current'] && (page.route === '/' ? node.attrs.href === '#overview' : node.attrs.href === page.route))), file, 'missing current navigation');
    const popup = nodes.find(node => (node.attrs.class || '') === 'projects-popup__list');
    check(popup && !popup.inner.includes('(current)') && !popup.inner.includes('>decompose<'), file, 'Decompose must not be added to pinned project set');
  }
  const landing = documents.get('index.html');
  const versions = landing?.nodes.filter(node => 'data-version' in node.attrs || 'data-release-version' in node.attrs) || [];
  check(versions.length === 2 && versions.every(node => text(node.inner) === `v${facts.version}`), 'index.html', 'rendered version differs from package.json');
  check(landing?.html.includes(facts.lead.replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[char])), 'index.html', 'landing introduction differs from README');
  const info = JSON.parse(readFileSync(join(dist, 'build-info.json'), 'utf8'));
  check(info.packageVersion === facts.version && info.mode === (live ? 'live' : 'default') && info.pageCount === pages.length && /^[a-f\d]{40}$/i.test(info.commit) && Number.isFinite(Date.parse(info.buildTime)), 'build-info.json', 'invalid build provenance');
  const robots = readFileSync(join(dist, 'robots.txt'), 'utf8');
  check(live ? robots.includes('Allow: /') && robots.includes(`Sitemap: ${origin}/sitemap.xml`) : robots === 'User-agent: *\nDisallow: /\n', 'robots.txt', 'wrong discovery policy');
  if (!live) for (const file of ['sitemap.xml', 'llms.txt', 'llms-full.txt']) check(!existsSync(join(dist, file)), file, 'forbidden in default mode');
  else {
    const sitemap = readFileSync(join(dist, 'sitemap.xml'), 'utf8');
    const locations = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match => match[1]);
    check(locations.length === pages.length && pages.every(page => locations.includes(origin + page.route)), 'sitemap.xml', 'sitemap differs from page map');
  }
  const png = readFileSync(join(dist, 'assets/social-preview.png'));
  check(png.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10])) && png.readUInt32BE(16) === 1200 && png.readUInt32BE(20) === 630, 'assets/social-preview.png', 'expected 1200x630 PNG');
  return [...new Set(failures)];
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2), options = {};
    for (let i = 0; i < args.length; i++) {
      if (args[i] === '--live') options.live = true;
      else if (args[i] === '--dist' && args[i + 1]) options.dist = resolve(args[++i]);
      else throw Error('Usage: node website/check.mjs [--live] [--dist <dir>]');
    }
    const failures = checkSite(options);
    failures.forEach(failure => console.error(failure));
    console.log(`${failures.length} failure(s).`);
    process.exitCode = failures.length ? 1 : 0;
  } catch (error) { console.error(error.stack); process.exitCode = 1; }
}
