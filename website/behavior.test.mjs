import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupCopy } from './assets/site.js';
import { setupGifTrailer } from './assets/trailer.js';
import { renderMarkdown } from './build.mjs';

test('clipboard denial keeps the install command visible and announces fallback', async () => {
  let click;
  const command = { textContent: 'npx aunx-decompose install', hidden: false };
  const status = { textContent: '', dataset: { fallback: 'Select the install command to copy it.' } };
  const button = { dataset: { copy: 'install-command' }, addEventListener: (_, handler) => { click = handler; } };
  const doc = { querySelectorAll: () => [button], getElementById: id => id === 'copy-status' ? status : command };
  setupCopy(doc, { writeText: async () => { throw Error('Clipboard denied'); } });
  await click();
  assert.equal(command.textContent, 'npx aunx-decompose install');
  assert.equal(command.hidden, false);
  assert.equal(status.textContent, status.dataset.fallback);
});

test('reduced motion shows the GIF poster until manual play; pause restores it', () => {
  const handlers = {}, attributes = {};
  const label = { textContent: '' };
  const poster = { hidden: false };
  const animation = { hidden: true, dataset: { src: '/assets/trailer.gif' }, removeAttribute: name => { delete animation[name]; } };
  const button = { addEventListener: (name, fn) => { handlers[name] = fn; }, setAttribute: (name, value) => { attributes[name] = value; }, getAttribute: name => attributes[name], querySelector: () => label };
  const container = { querySelector: selector => selector === '[data-poster]' ? poster : animation };
  const preference = { matches: true, addEventListener() {} };
  setupGifTrailer(container, button, { matchMedia: () => preference }, { hidden: false, addEventListener() {} });
  assert.equal(poster.hidden, false);
  assert.equal(animation.src, undefined);
  assert.equal(attributes['aria-label'], 'Play trailer');
  handlers.click();
  assert.equal(animation.src, '/assets/trailer.gif');
  assert.equal(poster.hidden, true);
  assert.equal(attributes['aria-label'], 'Pause trailer');
  handlers.click();
  assert.equal(poster.hidden, false);
  assert.equal(animation.src, undefined);
});

test('Markdown renderer drops active HTML and unsafe URL schemes', () => {
  const html = renderMarkdown('<script>alert(1)</script>\n\n[bad](javascript:alert)\n\n![bad](https://untrusted.example/x.png)\n\n`<img onerror=alert>`');
  assert.ok(!html.includes('<script'));
  assert.ok(!html.includes('href="javascript:'));
  assert.ok(!html.includes('src="https:'));
  assert.ok(html.includes('&lt;img onerror=alert&gt;'));
});
