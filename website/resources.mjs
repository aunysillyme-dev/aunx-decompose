import { existsSync } from 'node:fs';
export const hasVideo = ['trailer.mp4', 'trailer.webm'].every(file => existsSync(new URL(`assets/${file}`, import.meta.url)));
export const assets = ['site.css', 'site.js', 'navigation.js', 'trailer.js', 'projects-popup.css', 'projects-popup.js', 'avatar.png', 'social-preview.svg', 'social-preview.png', 'trailer.gif', 'trailer-poster.png', ...(hasVideo ? ['trailer.mp4', 'trailer.webm'] : [])];
export const fontStylesheet = 'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap';
export const csp = "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'self' https://fonts.googleapis.com; script-src 'self'; connect-src 'self'; font-src https://fonts.gstatic.com; base-uri 'none'; form-action 'none'";

export function fontLink(node) {
  if (node.name !== 'link') return false;
  const { rel, href } = node.attrs;
  return rel === 'stylesheet' && href === fontStylesheet
    || rel === 'preconnect' && ['https://fonts.googleapis.com', 'https://fonts.gstatic.com'].includes(href);
}

export function fontFile(url) {
  return url.origin === 'https://fonts.gstatic.com' && !url.username && !url.password
    && /^\/s\/(?:cormorantgaramond|jetbrainsmono)\/[a-zA-Z0-9_./-]+\.woff2?$/.test(url.pathname) && !url.search && !url.hash;
}
