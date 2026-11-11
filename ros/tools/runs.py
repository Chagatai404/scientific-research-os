"""Tools for durable runs, bounded output checkpoints and operation references."""
from .. import execution, runs
from ..registry import P, tool

# The runtime's session scope (ros/execution.py ``session_scope``): it reaches it through ``api``, never by importing the domain.
session_scope = execution.session_scope


def _worker(what):
    if not execution.in_worker():
        raise ValueError(f'Only the operations worker {what}: a client cannot keep a turn alive or take the person\'s steering messages.')


@tool('run_list', 'Read saved runs including explicit terminal states and committed tool results.', limit=P('integer', 'maximum rows'))
def listing(rec, limit=100): return runs.listing(rec, limit)

@tool('run_pending', 'Read the incrementally maintained active run set, including older runs beyond history pagination.')
def pending(rec): return runs.pending(rec)

@tool('run_get', 'Inspect one saved execution and its partial output and operation references.', run=P('string', 'run id', True))
def get(rec, run): return runs.get(rec, run)

@tool('run_start', 'Claim one queued run once across interfaces, without repeating committed effects.', writes=True, run=P('string', 'run id', True))
def start(rec, run): return runs.start(rec, run)

@tool('run_transition', 'Record a validated execution lifecycle transition without inferring completion from age.', writes=True, run=P('string', 'run id', True), state=P('string', 'next state', True), detail=P('string', 'safe status details'))
def transition(rec, run, state, detail=''): return runs.transition(rec, run, state, detail)

@tool('run_output', 'Checkpoint a batch of partial output, preserving it across reconnects and crashes.', writes=True, run=P('string', 'run id', True), text=P('string', 'output batch', True), final=P('boolean', 'the final flush after a stop, still kept on a cancelled or interrupted run'))
def output(rec, run, text, final=False): return runs.output(rec, run, text, final)

@tool('run_heartbeat', 'Record that the worker of a running turn is alive. A turn silent for too long reads as interrupted; a finished turn is never revived.', writes=True, run=P('string', 'run id', True))
def heartbeat(rec, run):
    _worker('records a turn\'s heartbeat')
    return runs.heartbeat(rec, run)

@tool('run_follow', 'Read the output of a run from a cursor (characters already seen), with its state, so a reloaded or reopened client resumes without repeated or missing text.', run=P('string', 'run id', True), after=P('integer', 'cursor returned by the previous read; 0 to start'))
def follow(rec, run, after=0): return runs.follow(rec, run, after)

@tool('run_steer_take', 'Claim the steering messages the person queued on a running turn, once each, to give to the model at a tool boundary.', writes=True, run=P('string', 'run id', True))
def steer_take(rec, run):
    _worker('claims steering messages')
    return runs.take_steers(rec, run)

@tool('run_step', 'Record a committed operation result exactly once for its operation identifier.', writes=True, run=P('string', 'run id', True), operation=P('string', 'idempotency key', True), tool_name=P('string', 'tool name', True), result=P('any', 'canonical result', True))
def step(rec, run, operation, tool_name, result): return runs.step(rec, run, operation, tool_name, result)

@tool('run_usage', 'Preserve provider-reported usage and cost distinctly from unavailable or estimated values.', writes=True, run=P('string','run id',True), usage=P('object','reported token usage'), cost=P('number','reported provider cost, when available'))
def usage(rec,run,usage=None,cost=None):return runs.usage(rec,run,usage,cost)

@tool('run_cancel', 'Stop a saved run, preserving its partial output and committed effects.', human=True,
      run=P('string', 'run id', True))
def cancel(rec, run):
    row = runs.get(rec, run)
    return row if row['state'] in runs.TERMINAL else runs.transition(rec, run, 'cancelled', 'Stopped by the researcher; partial output retained.')


@tool('run_sweep', 'Mark running turns whose worker stopped heartbeating as interrupted, keeping their partial output; fresh turns are left alone.', writes=True)
def sweep(rec): return runs.sweep(rec)
