"""Tools for durable runs, bounded output checkpoints and operation references."""
from .. import runs
from ..registry import P, tool

@tool('run_list', 'Read saved runs including explicit terminal states and committed tool results.', limit=P('integer', 'maximum rows'))
def listing(rec, limit=100): return runs.listing(rec, limit)

@tool('run_get', 'Inspect one saved execution and its partial output and operation references.', run=P('string', 'run id', True))
def get(rec, run): return runs.get(rec, run)

@tool('run_transition', 'Record a validated execution lifecycle transition without inferring completion from age.', writes=True, run=P('string', 'run id', True), state=P('string', 'next state', True), detail=P('string', 'safe status details'))
def transition(rec, run, state, detail=''): return runs.transition(rec, run, state, detail)

@tool('run_output', 'Checkpoint a batch of partial output, preserving it across reconnects and crashes.', writes=True, run=P('string', 'run id', True), text=P('string', 'output batch', True))
def output(rec, run, text): return runs.output(rec, run, text)

@tool('run_step', 'Record a committed operation result exactly once for its operation identifier.', writes=True, run=P('string', 'run id', True), operation=P('string', 'idempotency key', True), tool_name=P('string', 'tool name', True), result=P('any', 'canonical result', True))
def step(rec, run, operation, tool_name, result): return runs.step(rec, run, operation, tool_name, result)

@tool('run_usage', 'Preserve provider-reported usage and cost distinctly from unavailable or estimated values.', writes=True, run=P('string','run id',True), usage=P('object','reported token usage'), cost=P('number','reported provider cost, when available'))
def usage(rec,run,usage=None,cost=None):return runs.usage(rec,run,usage,cost)
