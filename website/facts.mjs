import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const rootDir = fileURLToPath(new URL('..', import.meta.url));
export const visibleText = value => String(value).replace(/<[^>]*>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
export function section(markdown, heading) {
  const lines = markdown.split('\n');
  const start = lines.findIndex(line => line === `## ${heading}`);
  if (start < 0) throw Error(`Missing source section: ${heading}`);
  let end = start + 1;
  while (end < lines.length && !lines[end].startsWith('## ')) end++;
  return lines.slice(start, end).join('\n').trim();
}
export function loadSourceFacts(root = rootDir) {
  // Site copy carries no em dashes; source Markdown that has one renders with a comma instead.
  const read = file => readFileSync(join(root, file), 'utf8').replace(/\s*\u2014\s*/g, ', ');
  const pkg = JSON.parse(read('package.json'));
  const readme = read('README.md');
  const lead = readme.split('\n\n').find(text => text.startsWith('Decompose is a plugin'));
  if (!lead) throw Error('README introduction missing');
  const method = readme.slice(readme.indexOf('\n1. Split the ask'), readme.indexOf('\nThe simpler step plans')).trim();
  if (!method.startsWith('1. ') || !method.includes('9. ')) throw Error('README method missing');
  const questions = section(readme, 'Questions');
  const faq = [...questions.matchAll(/^### (.+)\n\n([^]*?)(?=\n### |$)/gm)].map(match => ({ question: match[1], answerMarkdown: match[2].trim() }));
  const compatibility = faq.find(row => row.question === 'Which agents does it support?')?.answerMarkdown;
  if (!compatibility) throw Error('README compatibility missing');
  return { name: pkg.name, version: pkg.version, description: pkg.description, lead, method, faq, compatibility,
    npm: `https://www.npmjs.com/package/${pkg.name}`, readme, changelog: read('CHANGELOG.md'),
    skill: read('skills/decompose/SKILL.md'), command: read('commands/decompose.md'),
    picking: read('skills/decompose/references/picking.md'), recipes: JSON.parse(read('skills/decompose/recipes.json')) };
}
export function buildJsonLd(facts, { live = false } = {}) {
  const description = 'Open-source plugin and Python checker that splits complex prompts into numbered clauses, small verifiable units and parallel execution waves via npx.';
  if (!live) {
    return { '@context': 'https://schema.org', '@type': 'SoftwareApplication', name: 'Decompose',
      description, applicationCategory: 'DeveloperApplication', softwareRequirements: 'Python 3.8+',
      license: 'https://spdx.org/licenses/MIT.html', url: 'https://decompose.aunysillyme.dev/' };
  }
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'SoftwareSourceCode',
        '@id': 'https://decompose.aunysillyme.dev/#source',
        name: facts.name,
        description,
        url: 'https://decompose.aunysillyme.dev/',
        codeRepository: 'https://github.com/aunysillyme-dev/aunx-decompose',
        programmingLanguage: ['Python', 'JavaScript'],
        runtimePlatform: 'Python 3.8+, Node.js',
        version: facts.version,
        license: 'https://spdx.org/licenses/MIT.html',
        author: { '@id': 'https://aunysillyme.dev/#person' },
        sameAs: ['https://github.com/aunysillyme-dev/aunx-decompose', facts.npm]
      },
      {
        '@type': 'SoftwareApplication',
        '@id': 'https://decompose.aunysillyme.dev/#software',
        name: 'Decompose',
        description,
        url: 'https://decompose.aunysillyme.dev/',
        applicationCategory: 'DeveloperApplication',
        operatingSystem: 'macOS, Linux, Windows',
        softwareRequirements: 'Python 3.8+',
        softwareVersion: facts.version,
        isAccessibleForFree: true,
        license: 'https://spdx.org/licenses/MIT.html',
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
        author: { '@id': 'https://aunysillyme.dev/#person' },
        sameAs: ['https://github.com/aunysillyme-dev/aunx-decompose', facts.npm]
      },
      {
        '@type': 'Person',
        '@id': 'https://aunysillyme.dev/#person',
        name: 'Auny Hossain',
        alternateName: ['Auny', 'AunySillyMe'],
        url: 'https://aunysillyme.dev/',
        sameAs: [
          'https://www.aunysillyme.com/#person',
          'https://aunysillyme.com/',
          'https://github.com/aunysillyme',
          'https://github.com/aunysillyme-dev',
          'https://www.npmjs.com/~aunysillyme',
          'https://x.com/AunySillyMe'
        ]
      }
    ]
  };
}
export function buildFaqJsonLd(facts) {
  return { '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: facts.faq.map(row => ({
    '@type': 'Question', name: row.question, acceptedAnswer: { '@type': 'Answer', text: row.answerMarkdown.replace(/`|\*\*/g, '') } })) };
}
