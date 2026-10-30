import type {Run} from './Workbench';

const ROLE_LABELS: Record<string, string> = {scout: 'Literature scout', verifier: 'Source verifier', adversary: 'Adversary', librarian: 'Librarian', native: 'In your repository'};

function detail(result: unknown): string {
  if (typeof result === 'string') return result;
  const value = result as {command?: string; file_path?: string; files?: string[]; exit?: number | null} | null;
  if (!value) return '';
  if (value.command) return '$ ' + value.command + (value.exit != null && value.exit !== 0 ? ` (exit ${value.exit})` : '');
  if (value.file_path) return value.file_path;
  if (value.files) return value.files.join(', ');
  return '';
}

/** What the running turn has done so far, in order: the session's own tool calls; grouped, the work of each independent role
 * it delegated to (committed as `<role>:<tool>` while the role runs); and, in a Code session, each file edit and command
 * Claude Code or Codex made in the repository (`native:<tool>`), with what it ran. */
export function RunSteps({steps}: {steps: Run['steps']}) {
  const groups: {role: string; tools: string[]}[] = [];
  for (const step of steps) {
    const [role, tool] = step.tool.includes(':') ? step.tool.split(':', 2) : ['', step.tool];
    const label = role === 'native' ? [tool, detail(step.result)].filter(Boolean).join(': ') : tool;
    const last = groups.at(-1);
    if (role && last?.role === role) last.tools.push(label);
    else if (step.tool === 'delegate' && last && last.role === ((step.result as {role?: string})?.role || '')) last.tools.push('report');
    else groups.push({role, tools: [step.tool === 'delegate' ? 'report from ' + ((step.result as {role?: string})?.role || 'role') : label]});
  }
  return <details className="run-steps" open aria-label="What the session is doing"><summary>{steps.length} {steps.length === 1 ? 'step' : 'steps'} so far</summary><ol>{groups.map((group, index) => <li key={index} className={group.role ? 'role-step' : undefined}>{group.role === 'native' ? <><strong>{ROLE_LABELS.native}</strong> <small>its own file and shell tools</small><ul className="native-steps">{group.tools.map((t, i) => <li key={i}><code>{t}</code></li>)}</ul></> : group.role ? <><strong>{ROLE_LABELS[group.role] || group.role}</strong> <small>independent, fresh context</small><span>{group.tools.map(t => t.replaceAll('_', ' ')).join(' → ')}</span></> : <span>{group.tools.map(t => t.replaceAll('_', ' ')).join(' → ')}</span>}</li>)}</ol></details>;
}
