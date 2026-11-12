"""Tools for the usage and cost meter: reported usage per conversation or workspace, and the person's own price table."""
from .. import usage
from ..registry import P, tool

@tool('usage_summary', 'Sum the usage providers reported (tokens, requests) per provider and model for a conversation or a workspace, with the number of runs whose provider reported none (unknown, never estimated), a cost only where the person configured a price, and the context size of a conversation against its limit.',
      scope=P('string', 'conversation, workspace or record', enum=('conversation', 'workspace', 'record')), id=P('string', 'conversation id, for the conversation scope'), since=P('string', 'only runs from this ISO timestamp on'))
def summary(rec, scope='workspace', id=None, since=None): return usage.summary(rec, scope, id, since)

@tool('usage_prices', 'Read the configured prices per million tokens, every version, per model. No price exists until the person configures it.')
def prices(rec): return usage.prices(rec)

@tool('usage_prices_configure', 'Record a price version for one model: input, output and optionally cached-input price per million tokens, a currency and the date it takes effect. Only the person sets prices.', human=True,
      model=P('string', 'profile id or model name as it appears on runs', True), input=P('number', 'price per million input tokens', True), output=P('number', 'price per million output tokens', True),
      effective=P('string', 'YYYY-MM-DD the price starts to apply', True), cached=P('number', 'price per million cached input tokens'), currency=P('string', 'three-letter currency code, default USD'))
def configure(rec, model, input, output, effective, cached=None, currency='USD'): return usage.configure_price(rec, model, input, output, cached, currency, effective)
