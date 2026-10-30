import type {Run} from './Workbench';
const ROLE_LABELS: Record<string, string> = {scout: 'Literature scout', verifier: 'Source verifier', adversary: 'Adversary', librarian: 'Librarian'};

/** What the running turn has done so far, in order: the tutor's own tool calls and, grouped, the work of each independent
 * role it delegated to (each role's calls are committed as `<role>:<tool>` while it runs). */
export function RunSteps({steps}: {steps: Run['steps']}) {
  const groups: {role: string; tools: string[]}[] = [];
  for (const step of steps) {
    const [role, tool] = step.tool.includes(':') ? step.tool.split(':', 2) : ['', step.tool];
    const last = groups.at(-1);
    if (role && step.tool !== 'delegate' && last?.role === role) last.tools.push(tool);
    else if (step.tool === 'delegate' && last && last.role === ((step.result as {role?: string})?.role || '')) last.tools.push('report');
    else groups.push({role, tools: [step.tool === 'delegate' ? 'report from ' + ((step.result as {role?: string})?.role || 'role') : tool]});
  }
  return <details className="run-steps" open aria-label="What the session is doing"><summary>{steps.length} {steps.length === 1 ? 'step' : 'steps'} so far</summary><ol>{groups.map((group, index) => <li key={index} className={group.role ? 'role-step' : undefined}>{group.role ? <><strong>{ROLE_LABELS[group.role] || group.role}</strong> <small>independent, fresh context</small><span>{group.tools.map(t => t.replaceAll('_', ' ')).join(' → ')}</span></> : <span>{group.tools.map(t => t.replaceAll('_', ' ')).join(' → ')}</span>}</li>)}</ol></details>;
}
