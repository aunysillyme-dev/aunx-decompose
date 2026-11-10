import { loadSourceFacts } from './facts.mjs';
const facts = loadSourceFacts();
export const content = {
  brand: 'Decompose', eyebrow: 'CHECKABLE UNITS AND PARALLEL WAVES',
  headline: 'Break a task into the smallest units that can each be checked.',
  headlineAccent: 'See which units can run at the same time.',
  heroLede: facts.lead,
  install: { command: 'npx aunx-decompose install', copy: 'Copy install command', copySuccess: 'Install command copied.', copyFallback: 'Select the install command to copy it.' },
  nav: [
    { label: 'Overview', href: '#overview' }, { label: 'How it works', href: '#how-it-works' },
    { label: 'Watch the trailer', href: '#trailer' }, { label: 'Install', href: '#quickstart' },
    { label: 'Documentation', href: '#reference' }, { label: 'Compatibility', href: '#compatibility' },
    { label: 'Questions', href: '#questions' }, { label: 'Changelog', href: '#releases' },
  ],
  docsLabel: 'DOCUMENTATION', onThisPage: 'On this page', projectLinks: 'Project links',
  skip: 'Skip to content', sourceLabel: 'From', footer: { repository: 'View on GitHub', source: 'Source' },
  breadcrumbs: { label: 'Breadcrumb' },
  socialAlt: 'Decompose: checkable units, parallel waves and a plan a script can verify.',
  discovery: { install: 'Install:', pages: 'Site pages', source: 'Package sources', readme: 'GitHub README', npm: 'npm package' },
  notFound: { title: 'Page not found', text: 'Open the overview or choose a page from the documentation.', link: 'Open the overview' },
};
export default content;
