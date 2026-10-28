import {visit} from 'unist-util-visit';
import type {Root, Parent, Text, RootContent} from 'mdast';
import type {Plugin} from 'unified';

const labels: Record<string, string> = {
  definition: 'Definition', rule: 'Rule', keyidea: 'Key Idea', mistake: 'Common Slip', remark: 'Note',
  example: 'Example', exercise: 'Exercise', question: 'Recall', warning: 'Warning', note: 'Note',
  theorem: 'Theorem', proof: 'Proof',
};
type Directive = Parent & {name: string; data?: {directiveLabel?: boolean; hName?: string; hProperties?: Record<string, unknown>}};

// Adapt only the old handout's fence headers and answer separators. The general
// parser remains remark, line numbers stay intact, and the canonical source is never changed.
export function legacyHandoutSyntax(source: string): string {
  const containers: {width: number; kind: string}[] = [];
  // A directive closer can otherwise win over a literal ::: inside fenced code
  // in micromark. Widen only real directive fences beyond all source colon runs.
  const padding = source.split('\n').reduce((width, line) => Math.max(width, /^\s*(:{3,})/.exec(line)?.[1].length || 0), 3);
  let fence: {character: string; width: number} | undefined;
  return source.split('\n').map(line => {
    // Recognize fences nested under list items too. Conservatively leaving an
    // indented fence untouched is preferable to interpreting its sample syntax.
    const code = /^(?:[ \t]*(?:[-+*]|\d+[.)])[ \t]+)?[ \t]*(`{3,}|~{3,})(.*)$/.exec(line);
    if (fence) {
      if (code && code[1][0] === fence.character && code[1].length >= fence.width && !code[2].trim()) fence = undefined;
      return line;
    }
    if (code) {fence = {character: code[1][0], width: code[1].length}; return line;}
    const close = /^ {0,3}(:{3,})\s*$/.exec(line);
    if (close) {
      const active = containers.length > 0;
      while (containers.length && containers.at(-1)!.width <= close[1].length) containers.pop();
      return active ? line.replace(close[1], ':'.repeat(close[1].length + padding)) : line;
    }
    const open = /^( {0,3})(:{3,})([a-z][\w-]*)(.*)$/i.exec(line);
    if (open) {
      const kind = open[3].toLowerCase();
      containers.push({width: open[2].length, kind});
      const title = open[4].trim();
      if (labels[kind] && title && !/^[\[{]/.test(title)) {
        return `${open[1]}${':'.repeat(open[2].length + padding)}${kind}[${title.replace(/([\\\[\]])/g, '\\$1')}]`;
      }
      return line.replace(open[2], ':'.repeat(open[2].length + padding));
    }
    if (['example', 'exercise', 'question'].includes(containers.at(-1)?.kind || '') && /^ {0,3}===\s*(solution|answer)\s*$/i.test(line)) return '::ros-answer';
    return line;
  }).join('\n');
}

export const handoutCallouts: Plugin<[], Root> = () => tree => {
  visit(tree, node => {
    if (node.type !== 'containerDirective') return;
    const directive = node as unknown as Directive;
    if (directive.name === 'ros-solution') return;
    const kind = labels[directive.name] ? directive.name : 'note';
    directive.data = {...directive.data, hName: 'aside', hProperties: {className: ['callout'], dataKind: kind}};
    const title = directive.children.find(child => (child.data as Directive['data'])?.directiveLabel);
    const heading = {type: 'paragraph', data: {hProperties: {className: ['callout-title']}},
      children: [{type: 'strong', children: [{type: 'text', value: labels[kind]},
        ...(title && 'children' in title ? [{type: 'text', value: ' — '}, ...title.children] : [])]}]} as RootContent;
    directive.children = [heading, ...directive.children.filter(child => child !== title)];
    const split = directive.children.findIndex(child => child.type === 'leafDirective' && (child as unknown as Directive).name === 'ros-answer');
    if (split < 0 || !['example', 'exercise', 'question'].includes(kind)) return;
    const solution = directive.children.splice(split);
    directive.children.push({type: 'containerDirective', name: 'ros-solution',
      data: {hName: 'details', hProperties: {className: ['handout-solution']}}, children: [
        {type: 'paragraph', data: {hName: 'summary'}, children: [{type: 'text', value: kind === 'question' ? 'Answer' : 'Solution'}]},
        ...solution.slice(1),
      ]} as unknown as RootContent);
  });
};

export function blockAnchor(prefix: string, id: string): string {return `${prefix}-block-${id}`;}

// Obsidian-style ^ids opt blocks into identity that survives inserted paragraphs.
// Duplicate explicit ids get a deterministic suffix rather than duplicate DOM ids.
export function explicitBlocks(prefix: string): Plugin<[], Root> {
  return () => tree => {
    const used = new Set<string>();
    function walk(parent: Parent) {
      for (let index = 0; index < parent.children.length; index++) {
        const child = parent.children[index];
        if ('children' in child) walk(child as Parent);
        if (child.type !== 'paragraph' && child.type !== 'heading') continue;
        const last = child.children.at(-1);
        if (last?.type !== 'text') continue;
        const marker = /(?:^|\s)\^([A-Za-z0-9][A-Za-z0-9_-]{0,63})[ \t]*$/.exec(last.value);
        if (!marker) continue;
        const rest = last.value.slice(0, marker.index);
        const markerOnly = child.children.length === 1 && !rest.trim();
        const target = markerOnly ? parent.children[index - 1] : child;
        if (!target || !('children' in target || target.type === 'code' || target.type === 'thematicBreak')) continue;
        const base = blockAnchor(prefix, marker[1]);
        let id = base, count = 1;
        while (used.has(id)) id = `${base}-${++count}`;
        used.add(id);
        target.data = {...target.data, hProperties: {...target.data?.hProperties, id}};
        if (markerOnly) {parent.children.splice(index--, 1);} else {(last as Text).value = rest;}
      }
    }
    walk(tree);
  };
}
