import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {BinList, GrantList, PlanList, PlanPreview, purgeDays, RunStatus} from './ComputerWork';
import type {ComputerPlanView, ComputerStatus} from './contracts';

const view = (extra: Partial<ComputerPlanView> = {}): ComputerPlanView => ({plan: 'computer-plan:general-work:a', revision: 'abcdef1234567890', latest_revision: 'abcdef1234567890', status: 'awaiting_approval', workspace_id: 'ws:general', owner_record: 'general-work', steps: 1,
  preview: [{step: 'c', op: 'copy', text: 'Copy C:\\Downloads\\a.pdf to D:\\Stick', reversible: true, irreversible: false}], reversible: true,
  scope: {paths: [{path: 'C:\\Downloads', access: 'read'}, {path: 'D:\\Stick', access: 'write'}], ops: ['copy']},
  remember_roots: [{path: 'D:\\Stick', access: 'write'}], remember_ops: ['copy'], ...extra});
const html = (v: ComputerPlanView) => renderToStaticMarkup(<PlanPreview view={v}/>);

test('the preview shows steps, what is read and written, and what remember would allow before the buttons', () => {
  const out = html(view());
  assert.match(out, /Copy C:\\Downloads\\a\.pdf to D:\\Stick/); assert.match(out, /read<\/span> C:\\Downloads/); assert.match(out, /write<\/span> D:\\Stick/);
  assert.ok(out.indexOf('Later plans in this workspace') < out.indexOf('>Approve and remember'));
  assert.match(out, />Approve</); assert.match(out, />Reject</); assert.doesNotMatch(out, /Delete for good/);
});

test('a permanent delete and a payment are highlighted, and permanent delete has its own checkbox', () => {
  const out = html(view({preview: [
    {step: 'd', op: 'delete_permanent', text: 'Delete C:\\old.txt', reversible: false, irreversible: true, needs_your_approval_of_this_action: true},
    {step: 'p', op: 'spend', text: 'Pay 12 EUR to Acme for fees', amount: 12, currency: 'EUR', payee: 'Acme', purpose: 'fees', reversible: false, irreversible: true}]}));
  assert.match(out, /type="checkbox"[^>]*\/> Delete for good/); assert.match(out, /cannot be undone/);
  assert.match(out, /data-spend/); assert.match(out, /<dd>12 EUR<\/dd>/); assert.match(out, /<dd>Acme<\/dd>/); assert.match(out, /<dd>fees<\/dd>/);
  assert.match(out, /never remembered/);
});

test('an approved or stale plan offers no decision; a stale one says why', () => {
  assert.doesNotMatch(html(view({status: 'authorized'})), />Approve</);
  const stale = html(view({latest_revision: 'ffff'}));
  assert.match(stale, /changed after this revision/); assert.match(stale, /disabled=""[^>]*>Approve</);
});

test('live status shows verified steps with hashes and Cancel only while running', () => {
  const status = (state: string): ComputerStatus => ({...view({status: 'authorized'}), units: [{id: 'u', state, attempt: 2, plan: 'p', revision: 'r', result: null}],
    step_states: [{step: 'c', op: 'copy', phase: 'verified', action: 'a', sha256: 'abcdef0123456789ff', undone: false}]});
  const running = renderToStaticMarkup(<RunStatus status={status('running')}/>);
  assert.match(running, /1 of 1 steps verified/); assert.match(running, /<code>abcdef012345<\/code>/); assert.match(running, />Cancel</);
  assert.doesNotMatch(renderToStaticMarkup(<RunStatus status={status('completed')}/>), />Cancel</);
  assert.match(renderToStaticMarkup(<RunStatus status={status('interrupted')}/>), /not repeated/);
});

test('the bin shows the original path, the date and the days until the 30-day purge, with Restore', () => {
  const now = Date.parse('2026-11-11T12:00:00Z');
  assert.equal(purgeDays('2026-11-21T12:00:00Z', now), 10); assert.equal(purgeDays('2026-11-01T00:00:00Z', now), 0); assert.equal(purgeDays(null, now), null);
  const out = renderToStaticMarkup(<BinList now={now} bin={{workspace_id: 'w', retention_days: 30, items: [{action: 'computer-action:g:k', original: 'C:\\old\\x.txt', sha256: 'h', deleted_at: '2026-10-22T12:00:00Z', purge_after: '2026-11-21T12:00:00Z'}]}}/>);
  assert.match(out, /C:\\old\\x\.txt/); assert.match(out, /2026-10-22/); assert.match(out, /10 days/); assert.match(out, /aria-label="Restore C:\\old\\x\.txt"/);
  assert.match(renderToStaticMarkup(<BinList bin={{workspace_id: 'w', items: []}}/>), /bin is empty/);
});

test('standing grants list their folders and each has a labelled Revoke', () => {
  const out = renderToStaticMarkup(<GrantList grants={[{id: 'g', workspace_id: 'w', standing: true, roots: [{path: 'D:\\Stick', access: 'write'}], ops: ['copy'], revoked: false}]}/>);
  assert.match(out, /D:\\Stick/); assert.match(out, /aria-label="Revoke the grant for D:\\Stick"/);
  assert.match(renderToStaticMarkup(<GrantList grants={[]}/>), /No standing permission/);
});

test('proposed plans open on their own and a revoked grant shows as revoked without a Revoke button', () => {
  const plans = ['done', 'proposed'].map(state => ({plan: 'computer-plan:g:' + state, revision: 'r', state: state as 'done' | 'proposed', steps: 2, workspace_id: 'w', owner_record: 'g', unit: null}));
  const out = renderToStaticMarkup(<PlanList plans={plans} open={p => <i>{p.plan}</i>}/>);
  assert.ok(out.indexOf('proposed') < out.indexOf('done')); assert.match(out, /<details open=""><summary>proposed/); assert.doesNotMatch(out, /<details open=""><summary>done/);
  const grants = renderToStaticMarkup(<GrantList grants={[{id: 'g', workspace_id: 'w', standing: true, roots: [{path: 'D:\S', access: 'write'}], ops: ['copy'], revoked: true}]}/>);
  assert.match(grants, /revoked/); assert.doesNotMatch(grants, />Revoke</);
  assert.match(renderToStaticMarkup(<PlanList plans={[]} open={() => null}/>), /No plan yet/);
});

test('the request form engages first and binds a one-request grant to that conversation', async () => {
  const {readFileSync} = await import('node:fs');
  const src = readFileSync(new URL('./ComputerWork.tsx', import.meta.url), 'utf8');
  const engage = src.indexOf("'engage'"), grant = src.indexOf("'computer_grant'");
  assert.ok(engage > 0 && grant > engage, 'engage must come before computer_grant');
  assert.match(src, /!standing && out\.conversation \? \{request: out\.conversation\}/);
});
