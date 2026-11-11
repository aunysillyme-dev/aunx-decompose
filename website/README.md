# Decompose website

The zero-dependency Node >=22 builder renders eight pages from this repository's public
README, changelog, package metadata, command wrapper, skill and recipes. It reads the
trailer from `docs/aunx-decompose-trailer.gif` on each build. Product version comes from
`package.json`, not a separate release file. Page sources and routes live in `pages.mjs`,
source extraction in `facts.mjs`, and presentation copy in `content.mjs`.

## Build and check

From the repository root:

```sh
node website/build.mjs && node website/check.mjs
node website/build.mjs --live && node website/check.mjs --live
node --test website/red-cases.test.mjs website/behavior.test.mjs
```

Normal builds replace only `website/dist/`, which is git-ignored. Edit source files and
rebuild. The builder uses its own Markdown renderer and sanitizer, with no dependencies
and no build-time network requests. It strips active source HTML, escapes code, rejects
unsafe URL schemes and maps links to included docs or public GitHub sources.
The checker verifies the exact output inventory, package/display version agreement,
build provenance, internal files and anchors, metadata, noindex, discovery policy,
external-link attributes, one H1 per page, CSP and absence of em dashes in output copy.
Tests inject faults into temporary, isolated checker fixtures, never the site's dist.

## Discovery and deployment preparation

Default mode is a noindex preview with `User-agent: *` and `Disallow: /`. It has no
sitemap, Markdown twins, llms files, social metadata or sameAs properties. Live mode
adds all of those at `https://decompose.aunysillyme.dev`. The 404 keeps noindex.
`build-info.json` records the commit, build time, package version, mode and page count.
`VERCEL_GIT_COMMIT_SHA` takes precedence over `git rev-parse HEAD`.

Root `vercel.json` has no framework and no install command. It runs both the builder
and checker, adding `--live` to each only when `SITE_LIVE=1`. Its CSP matches the
reference resource policy, with additional standard security headers. The build output
is `website/dist`. The site is served at https://decompose.aunysillyme.dev from a Vercel
project linked to this repository with production branch `main`, so every push to `main`
rebuilds it. Compare `/build-info.json` on the site with the pushed commit to confirm a
deploy. Set `SITE_LIVE=1` only for the intended public deployment. No version or changelog edits in the website are needed for releases.

## Assets and trailer handoff

The current asset set includes the original Decompose GIF and a PNG poster extracted
with macOS sips. This lane is on macOS and cannot use ffmpeg here under the brief.
It has no granted Linux VM. Therefore MP4 and WebM conversion remains outstanding;
ffmpeg is present locally but was never invoked. The fallback GIF loops silently,
the 30px control swaps it to the poster on pause, and reduced motion starts on the
poster until manual play. Without JavaScript the poster and a GIF link remain visible.

On a permitted Linux VM with ffmpeg, run:

```sh
node website/prepare-trailer.mjs
node website/build.mjs && node website/check.mjs
node website/build.mjs --live && node website/check.mjs --live
```

The preparation script refuses non-Linux hosts. It generates a silent H.264 MP4, VP9
WebM and PNG poster in `website/assets`. The next build automatically selects the video
sources when both formats exist, with the reference reduced-motion and pause behavior.
The checked-in editable `assets/social-preview.svg` uses the reference portrait and
three-green bar treatment. Its rendered PNG is 1200x630. Refresh it locally with:

```sh
rsvg-convert -o website/assets/social-preview.png website/assets/social-preview.svg
```

The site uses the exact reference palette, 74px sticky header, 210px desktop sidebar,
two-column hero, JetBrains Mono at 400/500/600, outer-card rays, skip link and visible
focus. The popup uses the unchanged pinned set in `set.json`, with no current row and
without adding Decompose. The Home breadcrumb goes to `https://aunysillyme.dev`.
Browser QA at 375px and desktop remains unverified: both permitted headless Chrome
launch attempts exited 134 before loading the page. Behavior tests cover clipboard
denial, reduced-motion fallback/manual play, and Markdown sanitization independently.

## Source and reuse

Actual source copied from the public `aunysillyme/lean-browser-use` repository:
commit `e38f1ee812e3042be54af109339739b07ad193d6`.
The builder/renderer, checker HTML parser, templates, CSS, avatar, navigation, trailer
and project-popup implementation were copied before adapting Decompose facts.
`set.json` is copied unchanged from that commit's `.repo-build/set.json`.
The reference MIT license is preserved in `REFERENCE-LICENSE`.
Root `CREDITS.md` covers algorithmic ideas rather than internal website code reuse, so
it is unchanged. Product/package files and application configuration are unchanged.
`package.json` uses an explicit npm `files` allowlist that does not include `website` or
`vercel.json`, so this site adds nothing to the npm package contents.

Run `node --test website/red-cases.test.mjs website/behavior.test.mjs` for the acceptance
checks.
