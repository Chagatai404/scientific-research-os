import {useEffect, useState, type ReactNode} from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import remarkDirective from 'remark-directive';
import rehypeSanitize, {defaultSchema} from 'rehype-sanitize';
import rehypeKatex from 'rehype-katex';
import {visit} from 'unist-util-visit';
import type {Root as MdRoot, Text, Link, Parent as MdParent} from 'mdast';
import type {Root, Element} from 'hast';
import type {Plugin} from 'unified';
import {call, entityHref, href, routeOf, readDocument} from './api';
import type {DocumentData, Resolution} from './contracts';
import {useResource} from './hooks';
import {Notice} from './ui';

// Only this inline extension recognizes wikilinks and citation keys; Markdown parsing remains AST based.
const references: Plugin<[], MdRoot> = () => tree => {
  visit(tree, 'text', (node: Text, index, parent: MdParent | undefined) => {
    if (index == null || !parent || parent.type === 'link' || parent.type === 'linkReference') return;
    const pattern = /\[\[([^\]\n]+)\]\]|\[@([\w:.-]+)\]/g;
    const children: (Text | Link)[] = [];
    let cursor = 0;
    for (const match of node.value.matchAll(pattern)) {
      const at = match.index!;
      children.push({type: 'text', value: node.value.slice(cursor, at)});
      const [target, label] = (match[1] || '').split('|', 2);
      children.push({type: 'link', url: match[2] ? '#source-' + encodeURIComponent(match[2]) : '#resolve/' + encodeURIComponent(target),
        children: [{type: 'text', value: match[2] ? '[' + match[2] + ']' : label || target}]});
      cursor = at + match[0].length;
    }
    if (cursor) {children.push({type: 'text', value: node.value.slice(cursor)}); parent.children.splice(index, 1, ...children); return index + children.length;}
  });
};
// Only fenced container directives are part of our document contract. Inline `:name`
// directives conflict with canonical ids inside [[type:key]] and are deliberately disabled.
const containerDirectives: Plugin = function () {
  remarkDirective.call(this);
  const extensions = (this.data() as unknown as {micromarkExtensions?: {text?: unknown}[]}).micromarkExtensions;
  if (extensions?.length) delete extensions[extensions.length - 1].text;
};
const callouts: Plugin<[], MdRoot> = () => tree => {
  visit(tree, node => {
    if (node.type !== 'containerDirective') return;
    const directive = node as unknown as {name: string; data?: {hName?: string; hProperties?: Record<string, unknown>}};
    const kinds = new Set(['definition', 'example', 'exercise', 'question', 'warning', 'note', 'theorem', 'proof']);
    directive.data = {hName: 'aside', hProperties: {className: ['callout'], 'data-kind': kinds.has(directive.name) ? directive.name : 'note'}};
  });
};
// Anchors use source locations rather than heading text, preserving links through a heading rename of equal position.
function anchors(prefix: string): Plugin<[], Root> {
  return () => tree => {visit(tree, 'element', (node: Element) => {
    if (/^(h[1-6]|p|blockquote|pre|table)$/.test(node.tagName) && node.position) {
      node.properties.id = `${prefix}-b${node.position.start.line}`;
    }
  });};
}
const schema = {...defaultSchema, tagNames: [...defaultSchema.tagNames!, 'aside'], attributes: {
  ...defaultSchema.attributes,
  aside: ['className', 'dataKind'],
  code: [...(defaultSchema.attributes?.code || []), ['className', 'language-math', 'math-inline', 'math-display', 'language-mermaid']],
}};

export function safeUrl(value: string, image = false, base = '', record = ''): string {
  if (!value || /[\u0000-\u0020\u007f\\]/.test(value)) return '';
  if (value.startsWith('#')) return image ? '' : value;
  if (/^https?:\/\//i.test(value)) return image ? '' : value;
  if (!image && /^mailto:/i.test(value)) return value;
  if (!image && /^(capability|concept|course|claim|experiment|question|hypothesis|lesson|handout|source|paper|goal|project):/.test(value)) return entityHref(value, record);
  if (base && value.startsWith('figures/') && !value.split('/').includes('..')) value = base + value;
  if (value.startsWith('/media/') || (!image && value.startsWith('/vault/'))) {
    try {
      const decoded = decodeURIComponent(value.split('?')[0]);
      if (decoded.split('/').some(p => p === '..' || p === '.') || decoded.includes('\\') || decoded.startsWith('//')) return '';
    } catch {return '';}
    return value + (record && value.startsWith('/media/') ? (value.includes('?') ? '&' : '?') + 'record=' + encodeURIComponent(record) : '');
  }
  if (!image && value.startsWith('/workspace/')) return value;
  return '';
}

export function RichText({text, prefix = 'text', base = '', record = ''}: {text: string; prefix?: string; base?: string; record?: string}) {
  const [copied, setCopied] = useState(false);
  return <div className="rich-text">
    <Markdown remarkPlugins={[remarkGfm, remarkMath, containerDirectives, references, callouts]}
      rehypePlugins={[anchors(prefix), [rehypeSanitize, schema], [rehypeKatex, {trust: false, strict: 'warn', throwOnError: false}]]}
      skipHtml urlTransform={(url, key) => safeUrl(url, key === 'src', base, record)} components={{
        a: ({href: url, children, node: _node, ...props}) => {
          const next = url?.startsWith('#resolve/') ? href('resolve', decodeURIComponent(url.slice(9)), record) : url;
          const external = /^https?:/.test(next || '');
          return next ? <a {...props} href={next} onClick={event => {
            if (/^#(?:source-|user-content-|section-)/.test(next)) {
              event.preventDefault(); const current = routeOf(location.hash);
              location.hash = href(current.view, current.id, record, decodeURIComponent(next.slice(1)));
            }
          }} {...(external ? {target: '_blank', rel: 'noreferrer noopener'} : {})}>{children}</a> : <span className="unresolved">{children}</span>;
        },
        img: ({src, alt, title}) => src ? <span className="figure"><img src={src} alt={alt || 'Figure without a description'} title={title} loading="lazy" /><span className="caption">{title || alt}</span></span> : <span className="notice">Image unavailable: {alt || 'unsupported location'}</span>,
        table: ({children}) => <div className="table-wrap" role="region" aria-label="Scrollable table" tabIndex={0}><table>{children}</table></div>,
        pre: ({children}) => <pre tabIndex={0}>{children}</pre>,
      }}>{text}</Markdown>
    {text.includes('$') && <details className="math-source"><summary>Math source</summary><button onClick={async () => {try {await navigator.clipboard.writeText(text); setCopied(true);} catch {setCopied(false);}}}>{copied ? 'Copied' : 'Copy Markdown / LaTeX'}</button><pre tabIndex={0}>{text}</pre></details>}
  </div>;
}

export function DocumentView({id, record, onDocument}: {id: string; record: string; onDocument: (doc: DocumentData | null) => void}) {
  const resource = useResource('document:' + record + ':' + id, signal => readDocument(id, record, signal));
  useEffect(() => {onDocument(resource.data || null); return () => onDocument(null);}, [resource.data, onDocument]);
  if (!resource.data) return <Notice error={resource.error} retry={resource.retry} />;
  const doc = resource.data;
  return <article className="document"><div className="eyebrow">{doc.kind} <span>·</span> {doc.status}</div><h1>{doc.title}</h1>
    <p className="lead muted">{doc.legacy ? 'Preserved session · ' : ''}{doc.sections.filter(s => s.text).length} sections · {doc.record}</p>
    {doc.sections.filter(s => s.text.trim()).map(section => <section id={'section-' + section.id} key={section.id}>
      <h2><a className="heading-link" href={entityHref(doc.id, record, 'section-' + section.id)} aria-label={'Link to ' + section.title}>{section.title}<span aria-hidden="true"> ↗</span></a></h2>
      <RichText text={section.text} prefix={'section-' + section.id} base={doc.media_base} record={record} />
      {(section.by || section.locators?.length) ? <p className="section-meta">{section.by ? `Written by ${section.by}` : ''}{section.locators?.length ? ' · ' + section.locators.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join('; ') : ''}</p> : null}
    </section>)}
    {doc.sources.length > 0 && <section id="sources"><h2>Sources</h2><ol className="sources">{doc.sources.map(source => <li id={'source-' + source.key} key={source.key}><strong>[{source.key}]</strong> <RichText text={source.text} record={record} prefix={'source-' + source.key} /></li>)}</ol></section>}
    <footer className="document-footer"><span>Canonical record · {doc.id}</span><details><summary>Source fingerprint</summary><code>{doc.source_hash}</code></details></footer>
  </article>;
}

export function ResolveView({target, record}: {target: string; record: string}) {
  const result = useResource('resolve:' + record + ':' + target, signal => call<Resolution>('workspace_resolve', {target}, record, false, signal));
  if (!result.data) return <Notice error={result.error} retry={result.retry} />;
  return <><h1>{result.data.status === 'missing' ? 'Reference not found' : result.data.status === 'ambiguous' ? 'Choose the intended reference' : 'Resolved reference'}</h1>
    <p className="muted">{target}</p>{!result.data.matches.length && <p>The target may have moved or may not have been imported yet. Search by its title or canonical id.</p>}
    <ul className="entry-list">{result.data.matches.map(m => <li key={m.record + m.id}><a href={entityHref(m.id, m.record, m.anchor)}>{m.title}<small>{m.record} · {m.id}</small></a></li>)}</ul></>;
}
