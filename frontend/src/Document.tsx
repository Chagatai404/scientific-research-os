import {memo, useEffect, useState, type ReactNode} from 'react';
import {Mermaid, Excalidraw} from './Diagrams';
import Markdown, {type Components} from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import remarkDirective from 'remark-directive';
import rehypeSanitize, {defaultSchema} from 'rehype-sanitize';
import rehypeKatex from 'rehype-katex';
import {visit} from 'unist-util-visit';
import type {Root as MdRoot, Text, Link, Parent as MdParent} from 'mdast';
import type {Root, RootContent, Element} from 'hast';
import type {Plugin} from 'unified';
import {call, entityHref, href, routeOf, readDocument} from './api';
import type {DocumentData, Resolution} from './contracts';
import {useResource} from './hooks';
import {Notice} from './ui';
import {blockAnchor, explicitBlocks, handoutCallouts, legacyHandoutSyntax} from './documentSyntax';

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
// Preserve legacy line anchors beside explicit block identity. Line aliases describe
// this source revision; explicit ^ids remain stable when earlier paragraphs move.
function anchors(prefix: string): Plugin<[], Root> {
  return () => tree => {
    const used = new Set<string>();
    function walk(parent: Root | Element) {
      parent.children = (parent.children as RootContent[]).flatMap<RootContent>(child => {
        if (child.type !== 'element') return [child];
        if (child.tagName === 'pre') {
          const code = child.children.find(node => node.type === 'element' && node.tagName === 'code') as Element | undefined;
          if (code?.properties.id) {child.properties.id = code.properties.id; delete code.properties.id;}
        }
        walk(child);
        if (!/^(h[1-6]|p|blockquote|pre|table)$/.test(child.tagName) || !child.position) return [child];
        const old = `${prefix}-b${child.position.start.line}`;
        if (used.has(old)) return [child];
        used.add(old);
        if (!child.properties.id) {child.properties.id = old; return [child];}
        return [{type: 'element', tagName: 'span', properties: {id: old}, children: []} as Element, child];
      }) as typeof parent.children;
    }
    walk(tree);
  };
}
const schema = {...defaultSchema, tagNames: [...defaultSchema.tagNames!, 'aside'], attributes: {
  ...defaultSchema.attributes,
  aside: ['className', 'dataKind'],
  p: [...(defaultSchema.attributes?.p || []), ['className', 'callout-title']],
  details: [...(defaultSchema.attributes?.details || []), ['className', 'handout-solution']],
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

const ScientificCode: NonNullable<Components['code']> = ({children,className,node:_node,...props}) => className?.includes('language-mermaid') ? <Mermaid text={String(children)}/> : <code className={className} {...props}>{children}</code>;
export const RichText = memo(function RichText({text, prefix = 'text', base = '', record = ''}: {text: string; prefix?: string; base?: string; record?: string}) {
  const [copied, setCopied] = useState(false);
  return <div className="rich-text">
    <Markdown remarkPlugins={[remarkGfm, remarkMath, containerDirectives, references, handoutCallouts, explicitBlocks(prefix)]}
      rehypePlugins={[anchors(prefix), [rehypeSanitize, schema], [rehypeKatex, {trust: false, strict: 'warn', throwOnError: false}]]}
      skipHtml urlTransform={(url, key) => safeUrl(url, key === 'src', base, record)} components={{
        a: ({href: url, children, node: _node, ...props}) => {
          const block = /^#(?:\^|%5e)([A-Za-z0-9][A-Za-z0-9_-]{0,63})$/i.exec(url || '');
          const next = url?.startsWith('#resolve/') ? href('resolve', decodeURIComponent(url.slice(9)), record)
            : block ? '#user-content-' + blockAnchor(prefix, block[1]) : url;
          const external = /^https?:/.test(next || '');
          return next ? <a {...props} href={next} onClick={event => {
            if (/^#(?:source-|user-content-|section-)/.test(next)) {
              event.preventDefault(); const current = routeOf(location.hash);
              location.hash = href(current.view, current.id, record, decodeURIComponent(next.slice(1)));
            }
          }} {...(external ? {target: '_blank', rel: 'noreferrer noopener'} : {})}>{children}</a> : <span className="unresolved">{children}</span>;
        },
        img: ({src, alt, title}) => src ? <span className="figure">{/\.excalidraw(?:\?|$)/i.test(src)
          ? <a href={src}>Open Drawing Reference: {alt || 'Excalidraw Drawing'}</a>
          : <img src={src} alt={alt || 'Figure without a description'} title={title} loading="lazy" />}<span className="caption">{title || alt}</span></span> : <span className="notice">Image unavailable: {alt || 'unsupported location'}</span>,
        table: ({children, node: _node, ...props}) => <div className="table-wrap" role="region" aria-label="Scrollable table" tabIndex={0}><table {...props}>{children}</table></div>,
        pre: ({children, node: _node, ...props}) => <pre {...props} tabIndex={0}>{children}</pre>,
        code: ScientificCode,
      }}>{legacyHandoutSyntax(text)}</Markdown>
    {text.includes('$') && <details className="math-source"><summary>Math Source</summary><button onClick={async () => {try {await navigator.clipboard.writeText(text); setCopied(true);} catch {setCopied(false);}}}>{copied ? 'Copied' : 'Copy Markdown / LaTeX'}</button><pre tabIndex={0}>{text}</pre></details>}
  </div>;
});

export function DocumentView({id, record, onDocument}: {id: string; record: string; onDocument: (doc: DocumentData | null) => void}) {
  const resource = useResource('document:' + record + ':' + id, signal => readDocument(id, record, signal));
  useEffect(() => {onDocument(resource.data || null); return () => onDocument(null);}, [resource.data, onDocument]);
  if (!resource.data) return <Notice error={resource.error} retry={resource.retry} />;
  const doc = resource.data;
  function exportMarkdown() {const text = '# ' + doc!.title + '\n\n' + doc!.sections.map(s => '## ' + s.title + '\n\n' + s.text).join('\n\n'); const url = URL.createObjectURL(new Blob([text], {type:'text/markdown;charset=utf-8'})); const link = document.createElement('a'); link.href=url; link.download=doc!.title.replace(/[\\/:*?"<>|]/g,'-')+'.md'; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);}
  return <article className="document"><div className="eyebrow">{doc.kind} <span>·</span> {doc.status}</div><h1>{doc.title}</h1>
    <p className="lead muted">{doc.legacy ? 'Preserved session · ' : ''}{doc.sections.filter(s => s.text).length} sections · {doc.record}</p>
    {doc.sections.filter(s => s.text.trim()).map(section => <section id={'section-' + section.id} key={section.id}>
      <h2><a className="heading-link" href={entityHref(doc.id, record, 'section-' + section.id)} aria-label={'Link to ' + section.title}>{section.title}<span aria-hidden="true"> ↗</span></a></h2>
      <RichText text={section.text} prefix={'section-' + section.id} base={doc.media_base} record={record} />
      {(section.by || section.locators?.length) ? <p className="section-meta">{section.by ? `Written by ${section.by}` : ''}{section.locators?.length ? ' · ' + section.locators.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join('; ') : ''}</p> : null}
    </section>)}
    {doc.sources.length > 0 && <section id="sources"><h2>Sources</h2><ol className="sources">{doc.sources.map(source => <li id={'source-' + source.key} key={source.key}><strong>[{source.key}]</strong> <RichText text={source.text} record={record} prefix={'source-' + source.key} /></li>)}</ol></section>}
    <div className="actions document-actions"><button onClick={exportMarkdown}>Export Markdown</button><button onClick={()=>window.print()}>Print / Save PDF</button></div><footer className="document-footer"><span>Canonical record · {doc.id}</span><details><summary>Source Fingerprint</summary><code>{doc.source_hash}</code></details></footer>
  </article>;
}

export function ResolveView({target, record}: {target: string; record: string}) {
  const result = useResource('resolve:' + record + ':' + target, signal => call<Resolution>('workspace_resolve', {target}, record, false, signal));
  if (!result.data) return <Notice error={result.error} retry={result.retry} />;
  return <><h1>{result.data.status === 'missing' ? 'Reference Not Found' : result.data.status === 'ambiguous' ? 'Choose the Intended Reference' : 'Resolved Reference'}</h1>
    <p className="muted">{target}</p>{!result.data.matches.length && <p>The target may have moved or may not have been imported yet. Search by its title or canonical id.</p>}
    <ul className="entry-list">{result.data.matches.map(m => <li key={m.record + m.id}><a href={entityHref(m.id, m.record, m.anchor)}>{m.title}<small>{m.record} · {m.id}</small></a></li>)}</ul></>;
}
