"""Executable scientific verification: structured obligations, independent methods, scoped outcomes.

A spec names one claim and lists executable *checks*. The engine runs them and records a
scoped outcome plus exactly what was not verified. It never "verifies" free text: a claim
with no executable obligation is `not-checked`, a missing obligation is reported rather than
assumed, and successful execution is not scientific verification on its own.

Standard library only for the core. sympy, numpy, scipy, mpmath and statsmodels are optional
independent cross-checks: their absence can downgrade a check that required them, never
invalidate a correct result. Symbolic simplification is evidence, not proof.
Expressions are parsed from a whitelisted syntax tree and interpreted (no eval, no sympify).
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib
import json
import math
from pathlib import Path
import platform
import random
import re
import sys

SCHEMA = 1
OUTCOMES = ('verified-in-scope', 'partially-verified', 'invalidated', 'unresolved', 'not-checked')
PASS, FAIL, INCONCLUSIVE, ERROR = 'pass', 'fail', 'inconclusive', 'error'
CONSEQUENCES = ('routine', 'consequential')
QUANTITATIVE = ('evaluate', 'equivalent', 'integral', 'derivative', 'limit', 'rate-interval', 'propagation')
STRUCTURAL = ('dimensional', 'resampling-unit', 'fit-partition', 'assumption-declared', 'regime-match', 'mapping-declared')
KINDS = QUANTITATIVE + STRUCTURAL
CONTEXT_WORKFLOWS = {'math-review', 'statistics-review', 'physics-review', 'research-review', 'decision-synthesis', 'research-implement'}
SEVERITIES = ('A', 'B', 'C', 'D')  # the existing A-D research triage: A blocks, D is an optional refinement
MAX_EXPRESSION, MAX_NODES, MAX_CHECKS, MAX_POINTS = 2000, 400, 40, 2000
DEFAULT_TOLERANCE = {'rel': 1e-9, 'abs': 1e-12}
# Methods that cross-check but whose non-result must never downgrade a correct, otherwise-established check.
OPTIONAL_FAMILIES = {'symbolic', 'high-precision', 'library', 'approximation', 'monte-carlo'}
# Two families in one class are the same formulation done twice; a consequential claim needs two classes.
CLASS = {'exact-arithmetic': 'direct-evaluation', 'floating-point': 'direct-evaluation', 'high-precision': 'direct-evaluation',
         'sampling': 'direct-evaluation', 'symbolic': 'symbolic', 'quadrature': 'quadrature', 'analytic': 'analytic',
         'finite-difference': 'finite-difference', 'limit-sequence': 'limit-sequence', 'exact-interval': 'exact-interval',
         'library': 'independent-implementation', 'approximation': 'approximation',
         'linear-propagation': 'linear-propagation', 'monte-carlo': 'monte-carlo'}
# A high-precision rerun of the same integral or limit is the same method, not a second reconstruction.
CLASS_OVERRIDE = {('integral', 'high-precision'): 'quadrature', ('limit', 'high-precision'): 'limit-sequence'}


class VerificationError(ValueError):
    """Invalid spec, record or context. A ValueError so artifact readers degrade to 'invalid' instead of crashing."""

    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code = code


class ExpressionError(ValueError):
    pass


class DimensionError(ValueError):
    pass


class NotExact(Exception):
    pass


# --- optional libraries ---------------------------------------------------------------------

def optional(name):
    try:
        return importlib.import_module(name)
    except Exception:  # absent or broken: both mean "not available as an independent check"
        return None


def environment():
    libraries = {}
    for name in ('sympy', 'numpy', 'scipy', 'mpmath', 'statsmodels'):
        module = optional(name)
        libraries[name] = getattr(module, '__version__', 'available') if module else None
    return {'python': platform.python_version(), 'implementation': platform.python_implementation(),
            'platform': platform.platform(), 'tool': 'scientific_verify/' + str(SCHEMA), 'libraries': libraries}


# --- safe expression language ---------------------------------------------------------------

FUNCTIONS = {'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh', 'exp', 'log', 'log10', 'log2', 'sqrt',
             'abs', 'gamma', 'lgamma', 'erf', 'erfc', 'atan2', 'hypot', 'min', 'max'}
CONSTANTS = {'pi': math.pi, 'e': math.e, 'tau': math.tau}
ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Call, ast.Load,
           ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd)


def parse(expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > MAX_EXPRESSION:
        raise ExpressionError('expression must be nonempty text of bounded length')
    try:
        tree = ast.parse(expression.strip().replace('^', '**'), mode='eval')
    except SyntaxError as exc:
        raise ExpressionError(f'syntax error: {exc.msg}') from None
    count = 0
    for node in ast.walk(tree):
        count += 1
        if count > MAX_NODES:
            raise ExpressionError('expression is too large')
        if not isinstance(node, ALLOWED):
            raise ExpressionError(f'unsupported syntax: {type(node).__name__}')
        if isinstance(node, ast.Constant) and (type(node.value) not in (int, float) or not math.isfinite(node.value)):
            raise ExpressionError('only finite numeric constants are allowed')
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords or not 1 <= len(node.args) <= 4:
                raise ExpressionError('unsupported function call')
    return tree.body


def names(node):
    """Free variables of an expression (function names and constants excluded)."""
    found = set()

    def walk(n):
        if isinstance(n, ast.Call):
            for arg in n.args:
                walk(arg)
        elif isinstance(n, ast.Name):
            if n.id not in CONSTANTS:
                found.add(n.id)
        else:
            for child in ast.iter_child_nodes(n):
                walk(child)
    walk(node)
    return found


class FloatOps:
    family = 'floating-point'

    def const(self, v): return float(v)
    def variable(self, v): return v
    def name(self, n): return CONSTANTS[n]
    def add(self, a, b): return a + b
    def sub(self, a, b): return a - b
    def mul(self, a, b): return a * b
    def div(self, a, b): return a / b
    def neg(self, a): return -a

    def pow(self, a, b):
        return math.pow(a, b)  # raises ValueError for a negative base with a fractional exponent

    def func(self, name, args):
        if name == 'abs': return abs(args[0])
        if name == 'min': return min(args)
        if name == 'max': return max(args)
        return getattr(math, name)(*args)


class ExactOps:
    family = 'exact-arithmetic'

    def const(self, v): return Fraction(repr(v)) if isinstance(v, float) else Fraction(v)
    def variable(self, v): return _fraction(v)
    def name(self, n): raise NotExact(n)
    def add(self, a, b): return a + b
    def sub(self, a, b): return a - b
    def mul(self, a, b): return a * b
    def div(self, a, b): return a / b
    def neg(self, a): return -a

    def pow(self, a, b):
        if b.denominator != 1 or abs(b) > 64:
            raise NotExact('non-integer or large exponent')
        return a ** int(b)

    def func(self, name, args):
        if name == 'abs': return abs(args[0])
        if name == 'min': return min(args)
        if name == 'max': return max(args)
        raise NotExact(name)


class MultiPrecisionOps:
    family = 'high-precision'

    def __init__(self, mp):
        self.mp = mp

    def const(self, v): return self.mp.mpf(v)
    def variable(self, v): return v
    def name(self, n): return {'pi': self.mp.pi, 'e': self.mp.e, 'tau': 2 * self.mp.pi}[n]
    def add(self, a, b): return a + b
    def sub(self, a, b): return a - b
    def mul(self, a, b): return a * b
    def div(self, a, b): return a / b
    def neg(self, a): return -a

    def pow(self, a, b):
        result = self.mp.power(a, b)
        if isinstance(result, self.mp.mpc):
            if result.imag != 0:
                raise ValueError('complex result')
            return result.real
        return result

    def func(self, name, args):
        mp = self.mp
        if name == 'abs': return abs(args[0])
        if name == 'min': return min(args)
        if name == 'max': return max(args)
        if name == 'hypot': return mp.sqrt(args[0] ** 2 + args[1] ** 2)
        if name == 'lgamma': return mp.loggamma(args[0])
        if name == 'log10': return mp.log10(args[0])
        if name == 'log2': return mp.log(args[0], 2)
        value = getattr(mp, name)(*args)
        if isinstance(value, mp.mpc):
            if value.imag != 0:
                raise ValueError('complex result')
            value = value.real
        return value


EPS = 2.220446049250313e-16


def _partials(name, args):
    x = args[0]
    h = 1e-6 * max(1.0, abs(x))
    table = {'sin': lambda: [math.cos(x)], 'cos': lambda: [-math.sin(x)], 'tan': lambda: [1 / math.cos(x) ** 2],
             'asin': lambda: [1 / math.sqrt(1 - x * x)], 'acos': lambda: [-1 / math.sqrt(1 - x * x)], 'atan': lambda: [1 / (1 + x * x)],
             'sinh': lambda: [math.cosh(x)], 'cosh': lambda: [math.sinh(x)], 'tanh': lambda: [1 / math.cosh(x) ** 2],
             'exp': lambda: [math.exp(x)], 'log': lambda: [1 / x], 'log10': lambda: [1 / (x * math.log(10))],
             'log2': lambda: [1 / (x * math.log(2))], 'sqrt': lambda: [0.5 / math.sqrt(x)], 'abs': lambda: [1.0],
             'gamma': lambda: [(math.gamma(x + h) - math.gamma(x - h)) / (2 * h)],
             'lgamma': lambda: [(math.lgamma(x + h) - math.lgamma(x - h)) / (2 * h)],
             'erf': lambda: [2 / math.sqrt(math.pi) * math.exp(-x * x)], 'erfc': lambda: [-2 / math.sqrt(math.pi) * math.exp(-x * x)],
             'atan2': lambda: [args[1] / (args[0] ** 2 + args[1] ** 2), -args[0] / (args[0] ** 2 + args[1] ** 2)],
             'hypot': lambda: [a / math.hypot(*args) for a in args], 'min': lambda: [1.0] * len(args), 'max': lambda: [1.0] * len(args)}
    return table[name]()


class ErrorOps:
    """Running forward-error analysis: each value carries a first-order bound on its own floating-point error."""
    family = 'floating-point'

    def const(self, v):
        v = float(v)
        return v, 0.0 if v == int(v) and abs(v) < 2 ** 53 else EPS * abs(v)

    def variable(self, v): return float(v), 0.0
    def name(self, n): v = CONSTANTS[n]; return v, EPS * abs(v)
    def add(self, a, b): r = a[0] + b[0]; return r, a[1] + b[1] + EPS * abs(r)
    def sub(self, a, b): r = a[0] - b[0]; return r, a[1] + b[1] + EPS * abs(r)
    def neg(self, a): return -a[0], a[1]

    def mul(self, a, b):
        r = a[0] * b[0]
        return r, abs(a[0]) * b[1] + abs(b[0]) * a[1] + a[1] * b[1] + EPS * abs(r)

    def div(self, a, b):
        r = a[0] / b[0]
        return r, (a[1] + abs(r) * b[1]) / abs(b[0]) + EPS * abs(r)

    def pow(self, a, b):
        r = math.pow(a[0], b[0])
        err = EPS * abs(r)
        if a[1] and a[0] != 0:
            err += abs(b[0] * math.pow(a[0], b[0] - 1)) * a[1]
        if b[1] and a[0] > 0:
            err += abs(r * math.log(a[0])) * b[1]
        return r, err

    def func(self, name, args):
        values = [x[0] for x in args]
        r = FloatOps().func(name, values)
        try:
            err = sum(abs(p) * x[1] for p, x in zip(_partials(name, values), args)) + EPS * abs(r)
        except (ValueError, ZeroDivisionError, OverflowError):
            err = EPS * abs(r)
        return r, err


def interpret(node, env, ops, depth=0):
    if depth > 60:
        raise ExpressionError('expression is nested too deeply')
    if isinstance(node, ast.Constant):
        return ops.const(node.value)
    if isinstance(node, ast.Name):
        if node.id in env:
            return ops.variable(env[node.id])
        if node.id in CONSTANTS:
            return ops.name(node.id)
        raise ExpressionError(f'undefined variable {node.id}')
    if isinstance(node, ast.UnaryOp):
        value = interpret(node.operand, env, ops, depth + 1)
        return ops.neg(value) if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        a, b = interpret(node.left, env, ops, depth + 1), interpret(node.right, env, ops, depth + 1)
        return {ast.Add: ops.add, ast.Sub: ops.sub, ast.Mult: ops.mul, ast.Div: ops.div, ast.Pow: ops.pow}[type(node.op)](a, b)
    if isinstance(node, ast.Call):
        return ops.func(node.func.id, [interpret(arg, env, ops, depth + 1) for arg in node.args])
    raise ExpressionError('unsupported syntax')


def _fraction(value):
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NotExact('not a number')
    return Fraction(repr(value)) if isinstance(value, float) else Fraction(value)


def evaluate_float(tree, env):
    return interpret(tree, env, FloatOps())


def evaluate_exact(tree, env):
    return interpret(tree, env, ExactOps())


def evaluate_high_precision(tree, env, dps=50):
    mp = optional('mpmath')
    if mp is None:
        raise ImportError('mpmath')
    old = mp.mp.dps
    mp.mp.dps = dps
    try:
        return interpret(tree, {k: mp.mpf(str(v)) for k, v in env.items()}, MultiPrecisionOps(mp))
    finally:
        mp.mp.dps = old


def number(value, env=None):
    """A numeric literal, 'inf', or a small expression over declared parameters."""
    if isinstance(value, bool):
        raise ExpressionError('boolean is not a number')
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ExpressionError('non-finite number')
        return float(value)
    if value in ('inf', '+inf', 'Infinity'):
        return math.inf
    if value == '-inf':
        return -math.inf
    return evaluate_float(parse(value), env or {})


def close(a, b, tolerance):
    return math.isclose(a, b, rel_tol=tolerance['rel'], abs_tol=tolerance['abs'])


def tolerance_of(spec, check):
    merged = dict(DEFAULT_TOLERANCE)
    merged.update(spec.get('tolerance') or {})
    merged.update(check.get('tolerance') or {})
    for key in ('rel', 'abs'):
        if not isinstance(merged[key], (int, float)) or isinstance(merged[key], bool) or not 0 <= merged[key] < 1:
            raise VerificationError('SPEC_INVALID', f'tolerance.{key} must be a number in [0, 1)')
    return merged


# --- domain sampling ------------------------------------------------------------------------

def domain_of(spec, check, variables):
    declared = dict(spec.get('domain') or {})
    declared.update(check.get('domain') or {})
    out, defaulted = {}, []
    for name in sorted(variables):
        d = dict(declared.get(name) or {})
        if 'min' not in d or 'max' not in d:
            defaulted.append(name)
        lo, hi = float(d.get('min', -5.0)), float(d.get('max', 5.0))
        if not lo < hi:
            raise VerificationError('SPEC_INVALID', f'domain for {name} needs min < max')
        out[name] = {'min': lo, 'max': hi, 'exclude': [float(x) for x in d.get('exclude', [])], 'scale': d.get('scale', 'linear')}
    return out, defaulted


def excluded(x, d):
    return any(abs(x - bad) < 1e-12 for bad in d['exclude'])


def edge_values(d):
    lo, hi = d['min'], d['max']
    span = hi - lo
    candidates = [lo, hi, (lo + hi) / 2, lo + span * 1e-6, hi - span * 1e-6, -1.0, 1.0, 0.0, 1e-6, -1e-6, 2.0, -2.0, 0.5]
    return [x for x in dict.fromkeys(candidates) if lo <= x <= hi and not excluded(x, d)]


def sample_points(domain, count, seed):
    rng = random.Random(seed)
    order = sorted(domain)
    points, seen = [], set()
    edges = {n: edge_values(domain[n]) for n in order}
    for combo in range(min(64, max(1, math.prod(len(v) for v in edges.values())))):
        point = {n: edges[n][(combo * (i + 3)) % len(edges[n])] if edges[n] else domain[n]['min'] for i, n in enumerate(order)}
        key = tuple(sorted(point.items()))
        if key not in seen:
            seen.add(key)
            points.append(point)
    while len(points) < count:
        point = {}
        for n in order:
            d = domain[n]
            if d['scale'] == 'log' and d['min'] > 0:
                point[n] = math.exp(rng.uniform(math.log(d['min']), math.log(d['max'])))
            else:
                point[n] = rng.uniform(d['min'], d['max'])
        if not any(excluded(point[n], domain[n]) for n in order):
            points.append(point)
    return points


def try_value(tree, point):
    try:
        value = evaluate_float(tree, point)
    except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError, TypeError):
        return None, 'undefined'
    if isinstance(value, complex) or not math.isfinite(float(value)):
        return None, 'non-finite'
    return float(value), None


# --- numerical integration and differentiation (independent algorithms) ---------------------

XGK = (0.991455371120812639206854697526329, 0.949107912342758524526189684047851, 0.864864423359769072789712788640926,
       0.741531185599394439863864773280788, 0.586087235467691130294144838258730, 0.405845151377397166906606412076961,
       0.207784955007898467600689403773245, 0.0)
WGK = (0.022935322010529224963732008058970, 0.063092092629978553290700663189204, 0.104790010322250183839876322541518,
       0.140653259715525918745189590510238, 0.169004726639267902826583426598550, 0.190350578064785409913256402421014,
       0.204432940075298892414161999234649, 0.209482141084727828012999174891714)
WG = (0.129484966168869693270611432679082, 0.279705391489276667901467771423780,
      0.381830050505118944950369775488975, 0.417959183673469387755102040816327)


def gauss_kronrod(f, a, b):
    c, h = (a + b) / 2, (b - a) / 2
    center = f(c)
    kronrod, gauss = WGK[7] * center, WG[3] * center
    for i in range(7):
        x = h * XGK[i]
        pair = f(c - x) + f(c + x)
        kronrod += WGK[i] * pair
        if i % 2 == 1:
            gauss += WG[i // 2] * pair
    return kronrod * h, abs((kronrod - gauss) * h)


def adaptive_gk(f, a, b, tol, limit=400):
    intervals = [(a, b) + gauss_kronrod(f, a, b)]
    for _ in range(limit):
        total, error = sum(i[2] for i in intervals), sum(i[3] for i in intervals)
        if error <= max(tol['abs'], tol['rel'] * abs(total)):
            return total, error
        worst = max(range(len(intervals)), key=lambda k: intervals[k][3])
        lo, hi = intervals[worst][:2]
        mid = (lo + hi) / 2
        intervals[worst:worst + 1] = [(lo, mid) + gauss_kronrod(f, lo, mid), (mid, hi) + gauss_kronrod(f, mid, hi)]
    return sum(i[2] for i in intervals), sum(i[3] for i in intervals)


def tanh_sinh(f, a, b, levels=7):
    """Double-exponential quadrature on a finite interval; copes with endpoint singularities."""
    c, h0 = (a + b) / 2, (b - a) / 2
    previous = None
    for level in range(1, levels + 1):
        step = 2.0 ** -level
        total = 0.0
        for k in range(-int(7 / step), int(7 / step) + 1):
            t = k * step
            u = math.pi / 2 * math.sinh(t)
            x = math.tanh(u)
            if abs(x) >= 1.0 - 1e-15:
                continue
            weight = math.pi / 2 * math.cosh(t) / math.cosh(u) ** 2
            try:
                y = f(c + h0 * x)
            except (ValueError, ZeroDivisionError, OverflowError):
                continue
            if math.isfinite(y):
                total += weight * y
        value = total * step * h0
        if previous is not None and abs(value - previous) <= 1e-13 * max(1.0, abs(value)):
            return value
        previous = value
    return previous


def transform_bounds(f, lower, upper):
    """Map an infinite interval onto a finite one so both algorithms see the same finite problem."""
    if math.isinf(lower) and math.isinf(upper) and lower < upper:
        return (lambda t: f(t / (1 - t * t)) * (1 + t * t) / (1 - t * t) ** 2), -1.0, 1.0
    if math.isinf(upper) and not math.isinf(lower):
        return (lambda t: f(lower + t / (1 - t)) / (1 - t) ** 2), 0.0, 1.0
    if math.isinf(lower) and not math.isinf(upper):
        return (lambda t: f(upper - (1 - t) / t) / t ** 2), 0.0, 1.0
    return f, lower, upper


def derivative_central(f, x, h=None):
    """Richardson-extrapolated central difference."""
    h = h or max(1e-3, abs(x) * 1e-3)
    d = lambda step: (f(x + step) - f(x - step)) / (2 * step)
    return (4 * d(h / 2) - d(h)) / 3


# --- dimensional algebra (SI plus non-convertible material units) ---------------------------

class Dim(dict):
    """Exponents of base dimensions; non-SI bases (e.g. radiation lengths X0) never convert silently."""

    def __mul__(self, other):
        out = dict(self)
        for k, v in other.items():
            out[k] = out.get(k, Fraction(0)) + v
        return Dim({k: v for k, v in out.items() if v != 0})

    def inverse(self):
        return Dim({k: -v for k, v in self.items()})

    def power(self, p):
        return Dim({k: v * p for k, v in self.items() if v * p != 0})

    def __str__(self):
        return '*'.join(f'{k}^{v}' if v != 1 else k for k, v in sorted(self.items())) or 'dimensionless'


def _d(**kw):
    return Dim({k: Fraction(v) for k, v in kw.items()})


BASE_UNITS = {
    'm': (1.0, _d(L=1)), 'g': (1e-3, _d(M=1)), 's': (1.0, _d(T=1)), 'K': (1.0, _d(Theta=1)), 'mol': (1.0, _d(N=1)),
    'cd': (1.0, _d(J=1)), 'A': (1.0, _d(I=1)), 'rad': (1.0, Dim()), 'sr': (1.0, Dim()), 'deg': (math.pi / 180, Dim()),
    'Hz': (1.0, _d(T=-1)), 'N': (1.0, _d(M=1, L=1, T=-2)), 'Pa': (1.0, _d(M=1, L=-1, T=-2)),
    'J': (1.0, _d(M=1, L=2, T=-2)), 'W': (1.0, _d(M=1, L=2, T=-3)), 'C': (1.0, _d(I=1, T=1)),
    'V': (1.0, _d(M=1, L=2, T=-3, I=-1)), 'T': (1.0, _d(M=1, T=-2, I=-1)),
    'eV': (1.602176634e-19, _d(M=1, L=2, T=-2)), 'barn': (1e-28, _d(L=2)), 'b': (1e-28, _d(L=2)),
    # Radiation/interaction lengths depend on the material: deliberately their own dimensions.
    'X0': (1.0, _d(X0=1)), 'lambda_I': (1.0, _d(lambdaI=1)), 'MIP': (1.0, _d(MIP=1)), '1': (1.0, Dim()),
}
NO_PREFIX = {'1', 'X0', 'lambda_I', 'MIP'}
PREFIXES = {'y': 1e-24, 'z': 1e-21, 'a': 1e-18, 'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'm': 1e-3,
            'c': 1e-2, 'd': 1e-1, 'da': 1e1, 'h': 1e2, 'k': 1e3, 'M': 1e6, 'G': 1e9, 'T': 1e12, 'P': 1e15}


def unit_symbol(token):
    if token in BASE_UNITS:
        return BASE_UNITS[token]
    for prefix in sorted(PREFIXES, key=len, reverse=True):
        rest = token[len(prefix):]
        if token.startswith(prefix) and rest in BASE_UNITS and rest not in NO_PREFIX:
            scale, dim = BASE_UNITS[rest]
            return PREFIXES[prefix] * scale, dim
    raise VerificationError('UNIT_UNKNOWN', f'unknown unit {token!r}')


def parse_unit(text):
    """Units such as 'GeV', 'm/s^2', 'kg*m^2/s^2', 'J/(kg*K)', '1'. Returns (scale to SI, Dim)."""
    if not isinstance(text, str):
        raise VerificationError('UNIT_UNKNOWN', 'unit must be text')
    compact = text.replace(' ', '')
    tokens = re.findall(r'[A-Za-zµ_][A-Za-z0-9_µ]*|\d+|[*/^()]|-', compact)
    if ''.join(tokens) != compact or not tokens:
        raise VerificationError('UNIT_UNKNOWN', f'cannot read unit {text!r}')
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def factor():
        nonlocal pos
        token = peek()
        if token == '(':
            pos += 1
            value = expr()
            if peek() != ')':
                raise VerificationError('UNIT_UNKNOWN', f'unbalanced parentheses in {text!r}')
            pos += 1
        elif token is None:
            raise VerificationError('UNIT_UNKNOWN', f'incomplete unit {text!r}')
        else:
            pos += 1
            value = unit_symbol(token)
        if peek() == '^':
            pos += 1
            sign = 1
            if peek() == '-':
                sign, pos = -1, pos + 1
            exponent = peek()
            if exponent is None or not exponent.isdigit():
                raise VerificationError('UNIT_UNKNOWN', f'bad exponent in {text!r}')
            pos += 1
            p = Fraction(sign * int(exponent))
            value = (value[0] ** float(p), value[1].power(p))
        return value

    def expr():
        nonlocal pos
        value = factor()
        while peek() in ('*', '/'):
            op = peek()
            pos += 1
            other = factor()
            value = (value[0] * other[0], value[1] * other[1]) if op == '*' else (value[0] / other[0], value[1] * other[1].inverse())
        return value

    result = expr()
    if pos != len(tokens):
        raise VerificationError('UNIT_UNKNOWN', f'cannot read unit {text!r}')
    return result


def constant_exponent(node):
    try:
        return Fraction(repr(float(ast.literal_eval(ast.unparse(node))))).limit_denominator(1000)
    except (ValueError, SyntaxError, TypeError):
        return None


def dimension_of(node, units):
    """(scale, Dim) of an expression, or raise DimensionError naming the offending operation."""
    if isinstance(node, ast.Constant):
        return 1.0, Dim()
    if isinstance(node, ast.Name):
        if node.id in CONSTANTS:
            return 1.0, Dim()
        if node.id not in units:
            raise DimensionError(f'no unit declared for {node.id}')
        return parse_unit(units[node.id])
    if isinstance(node, ast.UnaryOp):
        return dimension_of(node.operand, units)
    if isinstance(node, ast.BinOp):
        (sa, da), (sb, db) = dimension_of(node.left, units), dimension_of(node.right, units)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            if da != db:
                raise DimensionError(f'cannot {"add" if isinstance(node.op, ast.Add) else "subtract"} [{da}] and [{db}]')
            return sa, da
        if isinstance(node.op, ast.Mult):
            return sa * sb, da * db
        if isinstance(node.op, ast.Div):
            return sa / sb, da * db.inverse()
        p = constant_exponent(node.right)
        if p is not None:
            return sa ** float(p), da.power(p)
        if db or da:
            raise DimensionError('a non-constant exponent of a dimensional quantity is not dimensionally defined')
        return 1.0, Dim()
    if isinstance(node, ast.Call):
        args = [dimension_of(a, units) for a in node.args]
        name = node.func.id
        if name == 'sqrt':
            return args[0][0] ** 0.5, args[0][1].power(Fraction(1, 2))
        if name in {'abs', 'min', 'max'}:
            if any(a[1] != args[0][1] for a in args):
                raise DimensionError(f'{name} of mixed dimensions')
            return args[0]
        if name in {'atan2', 'hypot'}:
            if args[0][1] != args[1][1]:
                raise DimensionError(f'{name} of mixed dimensions')
            return (1.0, Dim()) if name == 'atan2' else args[0]
        if any(a[1] for a in args):
            raise DimensionError(f'{name} needs a dimensionless argument, got [{args[0][1]}]')
        return 1.0, Dim()
    raise DimensionError('unsupported syntax')


# --- exact binomial intervals ---------------------------------------------------------------

def _betacf(a, b, x):
    tiny, qab, qap, qam = 1e-300, a + b, a + 1, a - 1
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def beta_cdf(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1 - x) / b


def beta_ppf(q, a, b):
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if beta_cdf(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k, n, confidence=0.95, sides=2):
    alpha = (1 - confidence) / (2 if sides == 2 else 1)
    lower = 0.0 if k == 0 else beta_ppf(alpha, k, n - k + 1)
    upper = 1.0 if k == n else beta_ppf(1 - alpha, k + 1, n - k)
    return (lower, upper) if sides == 2 else (0.0, upper)


def cholesky(matrix):
    n = len(matrix)
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                value = matrix[i][i] - s
                if value <= 0:
                    raise ValueError('not positive definite')
                lower[i][j] = math.sqrt(value)
            else:
                lower[i][j] = (matrix[i][j] - s) / lower[j][j]
    return lower


# --- checks ---------------------------------------------------------------------------------

def method(family, status, **detail):
    return {'family': family, 'status': status, **detail}


def unavailable(family, library):
    return {'family': family, 'status': 'unavailable', 'reason': f'{library} is not installed'}


def settle(methods, require=()):
    """Combine method results into a check status. An optional tool's silence never invalidates or downgrades."""
    if any(m['status'] == FAIL for m in methods):
        return FAIL
    core = [m for m in methods if m['family'] not in OPTIONAL_FAMILIES]
    if any(m['status'] == ERROR for m in core):
        return ERROR
    if [f for f in require if not any(m['family'] == f and m['status'] == PASS for m in methods)]:
        return INCONCLUSIVE
    if any(m['status'] == INCONCLUSIVE for m in core):
        return INCONCLUSIVE
    return PASS if any(m['status'] == PASS for m in methods) else INCONCLUSIVE


def run_evaluate(spec, check):
    tolerance = tolerance_of(spec, check)
    tree = parse(check['expression'])
    env = dict(check.get('variables') or {})
    missing = names(tree) - set(env)
    if missing:
        raise ExpressionError('undeclared variables: ' + ', '.join(sorted(missing)))
    expected = number(check['expected'], {k: v for k, v in env.items() if isinstance(v, (int, float))})
    methods = []
    try:
        exact = evaluate_exact(tree, env)
        methods.append(method('exact-arithmetic', PASS if close(float(exact), expected, tolerance) else FAIL,
                              value=str(exact), expected=expected))
    except (NotExact, ZeroDivisionError, TypeError):
        pass
    try:
        value = evaluate_float(tree, env)
        methods.append(method('floating-point', PASS if close(value, expected, tolerance) else FAIL, value=value, expected=expected))
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        methods.append(method('floating-point', ERROR, reason=str(exc)))
    if optional('mpmath'):
        try:
            value = float(evaluate_high_precision(tree, env))
            methods.append(method('high-precision', PASS if close(value, expected, tolerance) else FAIL, value=value, expected=expected))
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            methods.append(method('high-precision', ERROR, reason=str(exc)))
    else:
        methods.append(unavailable('high-precision', 'mpmath'))
    return methods


def float_error(tree, point):
    """First-order bound on the floating-point error of this expression at this point (0 when it cannot be bounded)."""
    try:
        _, err = interpret(tree, point, ErrorOps())
    except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError, TypeError):
        return 0.0
    return err if math.isfinite(err) else 0.0


def run_equivalent(spec, check):
    tolerance = tolerance_of(spec, check)
    lhs, rhs = parse(check['lhs']), parse(check['rhs'])
    variables = names(lhs) | names(rhs)
    domain, defaulted = domain_of(spec, check, variables)
    count = int(check.get('points', 200))
    if not 10 <= count <= MAX_POINTS:
        raise VerificationError('SPEC_INVALID', f'points must be between 10 and {MAX_POINTS}')
    seed = int(check.get('seed', 20260101))
    points = sample_points(domain, count, seed)
    compared = skipped = 0
    failures, soft = [], []
    loose = {'rel': max(tolerance['rel'], 1e-5), 'abs': max(tolerance['abs'], 1e-9)}
    for point in points:
        a, why_a = try_value(lhs, point)
        b, why_b = try_value(rhs, point)
        if a is None and b is None:
            skipped += 1
        elif a is None or b is None:
            failures.append({'point': point, 'lhs': a if a is not None else why_a, 'rhs': b if b is not None else why_b,
                             'reason': 'defined on one side only: the domains differ here'})
        elif close(a, b, tolerance):
            compared += 1
        elif close(a, b, loose) or abs(a - b) <= 2 * (float_error(lhs, point) + float_error(rhs, point)):
            # Within the expressions' own floating-point noise at this point: cancellation can do this to a correct identity.
            soft.append({'point': point, 'lhs': a, 'rhs': b})
        else:
            failures.append({'point': point, 'lhs': a, 'rhs': b, 'reason': 'values differ'})
    methods = []
    if failures:
        methods.append(method('sampling', FAIL, counterexample=failures[0], failures=len(failures), compared=compared, seed=seed))
        return methods
    artifacts = 0
    if soft:
        if not optional('mpmath'):
            methods.append(method('sampling', INCONCLUSIVE, rounding_level_points=len(soft), example=soft[0],
                                  reason='floating-point values disagree only at rounding level and high precision is unavailable '
                                         'to tell cancellation noise from a real difference'))
            methods.append(unavailable('high-precision', 'mpmath'))
            return methods
        for item in soft:
            try:
                a, b = float(evaluate_high_precision(lhs, item['point'])), float(evaluate_high_precision(rhs, item['point']))
            except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError):
                methods.append(method('sampling', INCONCLUSIVE, reason='a rounding-level disagreement could not be adjudicated', example=item))
                return methods
            if not close(a, b, {'rel': 1e-12, 'abs': 1e-14}):
                methods.append(method('sampling', FAIL, counterexample=dict(item, high_precision={'lhs': a, 'rhs': b}), failures=1,
                                      compared=compared, seed=seed, reason='confirmed at high precision'))
                return methods
            artifacts += 1
    if compared + artifacts >= 10:
        methods.append(method('sampling', PASS, compared=compared, skipped=skipped, seed=seed, domain_defaulted=defaulted,
                              float_artifacts_cleared_at_high_precision=artifacts))
    else:
        methods.append(method('sampling', INCONCLUSIVE, reason=f'only {compared} comparable points in the declared domain'))
    if optional('mpmath'):
        bad, tested = None, 0
        for point in points[:25]:
            try:
                a, b = float(evaluate_high_precision(lhs, point)), float(evaluate_high_precision(rhs, point))
            except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError):
                continue
            tested += 1
            if not close(a, b, {'rel': 1e-12, 'abs': 1e-14}):
                bad = {'point': point, 'lhs': a, 'rhs': b}
                break
        methods.append(method('high-precision', FAIL, counterexample=bad) if bad else method('high-precision', PASS, points=tested))
    else:
        methods.append(unavailable('high-precision', 'mpmath'))
    sp = optional('sympy')
    methods.append(symbolic_equivalence(sp, check) if sp else unavailable('symbolic', 'sympy'))
    return methods


def to_sympy(sp, node, symbols):
    if isinstance(node, ast.Constant):
        return sp.Rational(repr(node.value)) if isinstance(node.value, float) else sp.Integer(node.value)
    if isinstance(node, ast.Name):
        return {'pi': sp.pi, 'e': sp.E, 'tau': 2 * sp.pi}.get(node.id) or symbols.setdefault(node.id, sp.Symbol(node.id, real=True))
    if isinstance(node, ast.UnaryOp):
        value = to_sympy(sp, node.operand, symbols)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        a, b = to_sympy(sp, node.left, symbols), to_sympy(sp, node.right, symbols)
        return {ast.Add: sp.Add, ast.Sub: lambda x, y: x - y, ast.Mult: sp.Mul, ast.Div: lambda x, y: x / y, ast.Pow: sp.Pow}[type(node.op)](a, b)
    if isinstance(node, ast.Call):
        mapping = {'sin': sp.sin, 'cos': sp.cos, 'tan': sp.tan, 'asin': sp.asin, 'acos': sp.acos, 'atan': sp.atan, 'sinh': sp.sinh,
                   'cosh': sp.cosh, 'tanh': sp.tanh, 'exp': sp.exp, 'log': sp.log, 'sqrt': sp.sqrt, 'abs': sp.Abs, 'gamma': sp.gamma,
                   'erf': sp.erf, 'erfc': sp.erfc, 'atan2': sp.atan2, 'min': sp.Min, 'max': sp.Max,
                   'log10': lambda x: sp.log(x, 10), 'log2': lambda x: sp.log(x, 2), 'lgamma': sp.loggamma,
                   'hypot': lambda x, y: sp.sqrt(x ** 2 + y ** 2)}
        return mapping[node.func.id](*[to_sympy(sp, arg, symbols) for arg in node.args])
    raise ExpressionError('unsupported syntax')


def symbolic_equivalence(sp, check):
    """Symbolic simplification is evidence, not proof: failing to simplify to zero is inconclusive."""
    try:
        symbols = {}
        difference = to_sympy(sp, parse(check['lhs']), symbols) - to_sympy(sp, parse(check['rhs']), symbols)
        simplified = sp.simplify(difference)
        if simplified == 0:
            return method('symbolic', PASS, note='simplified to zero; evidence, not a proof over the stated domain')
        return method('symbolic', INCONCLUSIVE, residual=str(simplified)[:200],
                      reason='did not simplify to zero (this alone neither proves nor disproves equivalence)')
    except Exception as exc:  # sympy can fail in many ways on valid input
        return method('symbolic', INCONCLUSIVE, reason=f'{type(exc).__name__}: {exc}'[:200])


def run_integral(spec, check):
    tolerance = tolerance_of(spec, check)
    params = dict(check.get('params') or {})
    integrand = parse(check['integrand'])
    variable = check.get('variable', 'x')
    free = names(integrand) - set(params) - {variable}
    if free:
        raise ExpressionError('undeclared variables: ' + ', '.join(sorted(free)))
    lower, upper = number(check['lower'], params), number(check['upper'], params)
    if not lower < upper:
        raise VerificationError('SPEC_INVALID', 'integral needs lower < upper')
    f = lambda x: evaluate_float(integrand, {**params, variable: x})
    g, a, b = transform_bounds(f, lower, upper)
    compared = {}
    if 'expected' in check:
        compared['expected'] = number(check['expected'], params)
    analytic = None
    if 'analytic' in check:
        analytic = number(check['analytic'], params)
        compared['analytic'] = analytic
    methods = []
    try:
        value, error = adaptive_gk(g, a, b, {'rel': min(tolerance['rel'], 1e-10), 'abs': min(tolerance['abs'], 1e-13)})
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        return [method('quadrature', ERROR, reason=str(exc))]
    slack = {'rel': max(tolerance['rel'], 10 * error / max(abs(value), 1e-300)), 'abs': max(tolerance['abs'], 10 * error)}
    agree = {k: close(value, v, slack) for k, v in compared.items()}
    status = (PASS if all(agree.values()) else FAIL) if agree else INCONCLUSIVE
    quad = method('quadrature', status, algorithm='adaptive Gauss-Kronrod G7K15', value=value, error_estimate=error, compared=compared)
    try:
        cross = tanh_sinh(g, a, b)
        agrees = abs(cross - value) <= max(1e-6 * max(abs(value), 1e-300), 10 * error, tolerance['abs'])
        quad['cross_check'] = {'algorithm': 'tanh-sinh', 'value': cross, 'agrees': agrees}
        if not agrees:
            quad['status'] = FAIL
            quad['cross_check']['note'] = 'two quadrature algorithms disagree: the integral is not trustworthy as computed'
    except (ValueError, ZeroDivisionError, OverflowError):
        pass
    methods.append(quad)
    if analytic is not None and 'expected' in check:
        methods.append(method('analytic', PASS if close(analytic, compared['expected'], tolerance) else FAIL,
                              analytic=analytic, expected=compared['expected']))
    mp = optional('mpmath')
    if mp:
        try:
            mp.mp.dps = 30
            bounds = [mp.ninf if math.isinf(lower) else mp.mpf(lower), mp.inf if math.isinf(upper) else mp.mpf(upper)]
            hp = float(mp.quad(lambda x: evaluate_high_precision(integrand, {**params, variable: x}, 30), bounds))
            ok = all(close(hp, v, {'rel': max(tolerance['rel'], 1e-9), 'abs': max(tolerance['abs'], 1e-12)}) for v in compared.values())
            methods.append(method('high-precision', PASS if ok else FAIL, value=hp))
        except Exception as exc:  # mpmath quad can fail on hard integrands: "not run", not "wrong"
            methods.append(method('high-precision', INCONCLUSIVE, reason=f'{type(exc).__name__}: {exc}'[:160]))
    else:
        methods.append(unavailable('high-precision', 'mpmath'))
    return methods


def run_derivative(spec, check):
    base = tolerance_of(spec, check)
    tolerance = {'rel': max(base['rel'], 1e-6), 'abs': max(base['abs'], 1e-8)}
    function, expected = parse(check['function']), parse(check['expected'])
    variable = check.get('variable', 'x')
    params = dict(check.get('params') or {})
    free = (names(function) | names(expected)) - {variable} - set(params)
    if free:
        raise ExpressionError('undeclared variables: ' + ', '.join(sorted(free)))
    domain, defaulted = domain_of(spec, check, {variable})
    points = sample_points(domain, int(check.get('points', 40)), int(check.get('seed', 20260101)))
    failures, compared = [], 0
    for point in points:
        x = point[variable]
        try:
            approx = derivative_central(lambda t: evaluate_float(function, {**params, variable: t}), x)
            claimed = evaluate_float(expected, {**params, variable: x})
        except (ValueError, ZeroDivisionError, OverflowError):
            continue
        if not (math.isfinite(approx) and math.isfinite(claimed)):
            continue
        compared += 1
        if not close(approx, claimed, tolerance):
            failures.append({'x': x, 'finite_difference': approx, 'claimed': claimed})
    if failures:
        return [method('finite-difference', FAIL, counterexample=failures[0], failures=len(failures), compared=compared)]
    methods = [method('finite-difference', PASS, compared=compared, domain_defaulted=defaulted) if compared >= 5
               else method('finite-difference', INCONCLUSIVE, reason='too few differentiable sample points')]
    sp = optional('sympy')
    if sp:
        try:
            x_symbol = sp.Symbol(variable, real=True)
            symbols = {variable: x_symbol}
            residual = sp.simplify(sp.diff(to_sympy(sp, function, symbols), x_symbol) - to_sympy(sp, expected, symbols))
            methods.append(method('symbolic', PASS, note='evidence, not a proof') if residual == 0 else
                           method('symbolic', INCONCLUSIVE, residual=str(residual)[:160],
                                  reason='did not simplify to zero (neither proof nor disproof)'))
        except Exception as exc:
            methods.append(method('symbolic', INCONCLUSIVE, reason=f'{type(exc).__name__}: {exc}'[:160]))
    else:
        methods.append(unavailable('symbolic', 'sympy'))
    return methods


def run_limit(spec, check):
    base = tolerance_of(spec, check)
    tolerance = {'rel': max(base['rel'], 1e-6), 'abs': max(base['abs'], 1e-8)}
    tree = parse(check['expression'])
    variable = check.get('variable', 'x')
    target = number(check['approaching'])
    expected = number(check['expected'])
    params = dict(check.get('params') or {})
    directions = (1,) if math.isinf(target) else {'both': (1, -1), '+': (1,), '-': (-1,)}[check.get('direction', 'both')]
    high = optional('mpmath') is not None
    sequences = []
    for sign in directions:
        values = []
        for k in range(2, 9):
            x = (10.0 ** k) * (1 if target > 0 else -1) if math.isinf(target) else target + sign * 10.0 ** -k
            env = {**params, variable: x}
            try:
                values.append(float(evaluate_high_precision(tree, {n: repr(v) for n, v in env.items()}, 60)) if high
                              else evaluate_float(tree, env))
            except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError):
                values.append(math.nan)
        sequences.append(values)
    precision = 'high precision (60 digits)' if high else 'floating point'
    if not all(all(math.isfinite(v) for v in seq[:4]) for seq in sequences):
        return [method('limit-sequence', INCONCLUSIVE, reason='expression undefined or not finite along the approach', sequences=sequences)]
    estimates, stable = [], True
    for seq in sequences:
        finite = [v for v in seq if math.isfinite(v)]
        steps = [abs(finite[i] - finite[i - 1]) for i in range(1, len(finite))]
        best = min(range(len(steps)), key=lambda i: steps[i]) + 1
        estimates.append(finite[best])
        # Cancellation shows as steps that stop shrinking and then grow: the tail is noise, not a refutation.
        stable = stable and steps[-1] <= max(steps[best - 1] * 10, 1e-300) and len(finite) == len(seq)
    if all(close(v, expected, tolerance) for v in estimates):
        return [method('limit-sequence', PASS, estimates=estimates, precision=precision, stable_tail=stable)]
    if not stable:
        return [method('limit-sequence', INCONCLUSIVE, estimates=estimates, precision=precision,
                       reason='the sequence is numerically unstable (cancellation); rewrite the expression or use high precision')]
    return [method('limit-sequence', FAIL, estimates=estimates, expected=expected, precision=precision)]


def run_dimensional(spec, check):
    tree = parse(check['expression'])
    try:
        scale, dim = dimension_of(tree, dict(check['units']))
    except DimensionError as exc:
        return [method('dimensional', FAIL, reason=str(exc))]
    if 'expected_unit' in check:
        want_scale, want = parse_unit(check['expected_unit'])
        if dim != want:
            return [method('dimensional', FAIL, reason=f'expression has dimensions [{dim}], expected [{want}] ({check["expected_unit"]})')]
        return [method('dimensional', PASS, dimensions=str(dim), conversion_to_expected=scale / want_scale)]
    return [method('dimensional', PASS, dimensions=str(dim))]


def run_rate_interval(spec, check):
    k, n = check['successes'], check['trials']
    if not (isinstance(k, int) and isinstance(n, int) and not isinstance(k, bool) and 0 <= k <= n and n > 0):
        raise VerificationError('SPEC_INVALID', 'successes and trials must be integers with 0 <= successes <= trials, trials > 0')
    confidence, sides = float(check.get('confidence', 0.95)), int(check.get('sides', 2))
    if not 0.5 < confidence < 1 or sides not in (1, 2):
        raise VerificationError('SPEC_INVALID', 'confidence in (0.5, 1) and sides 1 or 2')
    tolerance = {'rel': max(tolerance_of(spec, check)['rel'], 1e-3), 'abs': 1e-12}
    lower, upper = clopper_pearson(k, n, confidence, sides)
    claimed = check.get('claimed') or {}
    problems = []
    interval = claimed.get('interval')
    if claimed.get('sigma') == 0 or (interval and interval[0] == interval[1]):
        problems.append('zero uncertainty claimed from finite counts')
    if interval:
        if interval[1] < upper * (1 - tolerance['rel']):
            problems.append(f'claimed upper bound {interval[1]:.6g} is below the exact {upper:.6g}')
        if lower > 0 and interval[0] > lower * (1 + tolerance['rel']):
            problems.append(f'claimed lower bound {interval[0]:.6g} is above the exact {lower:.6g}')
    rejection = claimed.get('rejection')
    if rejection:
        value = rejection.get('value')
        if k == 0 and (value in ('inf', 'Infinity') or (isinstance(value, float) and math.isinf(value))):
            problems.append('an infinite rejection factor cannot follow from zero observed events in finite trials')
        floor = 1.0 / upper if upper > 0 else math.inf
        if rejection.get('lower') is not None and rejection['lower'] > floor * (1 + tolerance['rel']):
            problems.append(f'claimed rejection lower bound {rejection["lower"]:.6g} exceeds the exact {floor:.6g}')
    methods = [method('exact-interval', FAIL if problems else PASS, algorithm='Clopper-Pearson (regularized incomplete beta)',
                      exact_interval=[lower, upper], confidence=confidence, sides=sides, problems=problems)]
    if k == 0 and sides == 1:
        approx = -math.log(1 - confidence) / n  # the "rule of three" generalized to this confidence
        methods.append(method('approximation', PASS if abs(approx - upper) <= 0.1 * upper else INCONCLUSIVE, rule_of_three=approx))
    stats = optional('scipy.stats') if optional('scipy') else None
    if stats:
        alpha = (1 - confidence) / (2 if sides == 2 else 1)
        s_lower = 0.0 if k == 0 else float(stats.beta.ppf(alpha, k, n - k + 1))
        s_upper = 1.0 if k == n else float(stats.beta.ppf(1 - alpha, k + 1, n - k))
        same = close(s_upper, upper, {'rel': 1e-6, 'abs': 1e-12}) and (sides == 1 or close(s_lower, lower, {'rel': 1e-6, 'abs': 1e-12}))
        methods.append(method('library', PASS if same else FAIL, scipy_interval=[s_lower, s_upper]))
    else:
        methods.append(unavailable('library', 'scipy'))
    return methods


def run_propagation(spec, check):
    tree = parse(check['function'])
    variables = check['variables']
    free = names(tree) - set(variables)
    if free:
        raise ExpressionError('undeclared variables: ' + ', '.join(sorted(free)))
    order = sorted(variables)
    values = {n: float(variables[n]['value']) for n in order}
    sigmas = {n: float(variables[n]['sigma']) for n in order}
    rho = {n: {m: 1.0 if n == m else 0.0 for m in order} for n in order}
    for pair, r in (check.get('correlations') or {}).items():
        a, b = [x.strip() for x in pair.split(',')]
        if a not in rho or b not in rho or not -1 <= float(r) <= 1:
            raise VerificationError('SPEC_INVALID', f'bad correlation {pair!r}')
        rho[a][b] = rho[b][a] = float(r)
    f = lambda env: evaluate_float(tree, env)
    gradient = {}
    for n in order:
        h = max(abs(values[n]) * 1e-6, 1e-9)
        gradient[n] = (f(dict(values, **{n: values[n] + h})) - f(dict(values, **{n: values[n] - h}))) / (2 * h)
    identity = {n: {m: 1.0 if n == m else 0.0 for m in order} for n in order}
    variance = lambda corr: sum(gradient[a] * gradient[b] * sigmas[a] * sigmas[b] * corr[a][b] for a in order for b in order)
    correct, naive = math.sqrt(max(variance(rho), 0.0)), math.sqrt(max(variance(identity), 0.0))
    tolerance = {'rel': max(tolerance_of(spec, check)['rel'], 1e-3), 'abs': 1e-12}
    claimed = float(check['claimed_sigma'])
    problems = []
    if not close(claimed, correct, tolerance):
        problems.append(f'claimed sigma {claimed:.6g} differs from the propagated {correct:.6g}')
        if close(claimed, naive, tolerance) and not close(naive, correct, tolerance):
            problems.append('the claim equals the independent-inputs result: stated correlations were ignored')
    methods = [method('linear-propagation', FAIL if problems else PASS, propagated_sigma=correct, independent_sigma=naive,
                      claimed_sigma=claimed, problems=problems)]
    cov = [[rho[a][b] * sigmas[a] * sigmas[b] for b in order] for a in order]
    try:
        chol = cholesky(cov)
    except ValueError:
        methods.append(method('monte-carlo', INCONCLUSIVE, reason='covariance is not positive definite'))
        return methods
    rng = random.Random(int(check.get('seed', 20260101)))
    samples = []
    for _ in range(int(check.get('samples', 20000))):
        z = [rng.gauss(0, 1) for _ in order]
        draw = {n: values[n] + sum(chol[i][j] * z[j] for j in range(i + 1)) for i, n in enumerate(order)}
        try:
            samples.append(f(draw))
        except (ValueError, ZeroDivisionError, OverflowError):
            continue
    if len(samples) > 100:
        mean = sum(samples) / len(samples)
        mc = math.sqrt(sum((s - mean) ** 2 for s in samples) / (len(samples) - 1))
        agree = abs(mc - correct) <= 0.05 * max(correct, 1e-300)
        methods.append(method('monte-carlo', PASS if agree else INCONCLUSIVE, monte_carlo_sigma=mc, samples=len(samples),
                              note=None if agree else 'linear propagation and sampling disagree: the function may be too nonlinear'))
    return methods


def run_resampling_unit(spec, check):
    resampled, independent = check['resampled_unit'], check['independent_unit']
    dependence = check.get('dependence', 'unknown')
    if dependence not in ('independent', 'correlated', 'unknown'):
        raise VerificationError('SPEC_INVALID', 'dependence is independent, correlated or unknown')
    if resampled == independent:
        return [method('structural', PASS, note=f'resampling the {resampled}, which is the independent unit')]
    if dependence == 'independent':
        return [method('structural', PASS, note='resampled units are declared independent')]
    if dependence == 'correlated':
        return [method('structural', FAIL, reason=f'resampling {resampled} as if independent, but they are correlated within each '
                                                  f'{independent}; the bootstrap must resample {independent}s')]
    return [method('structural', INCONCLUSIVE, reason=f'dependence between {resampled} units within a {independent} is not declared')]


def run_fit_partition(spec, check):
    leaks = [s['name'] for s in check['steps'] if set(s['fit_on']) & {'test', 'all'}
             and check.get('evaluated_on', 'test') in ('test', 'validation')]
    if leaks:
        return [method('structural', FAIL, reason='steps fit on data that includes the evaluation partition: ' + ', '.join(leaks), steps=leaks)]
    return [method('structural', PASS, note='every fitted step uses only the training partition')]


def run_assumption_declared(spec, check):
    declared = {a['id'] for a in spec.get('assumptions', [])}
    missing = [a for a in check['required'] if a not in declared]
    if missing:
        return [method('structural', INCONCLUSIVE, reason='required assumptions are not declared: ' + ', '.join(missing), missing=missing)]
    return [method('structural', PASS, declared=sorted(set(check['required'])))]


def run_regime_match(spec, check):
    gaps = []
    for key, target in check['target'].items():
        source = check['source'].get(key)
        if source is None:
            gaps.append(f'{key}: no source range declared')
        elif not (source[0] <= target[0] and target[1] <= source[1]):
            gaps.append(f'{key}: target {target} is outside the source range {source}')
    if gaps:
        return [method('structural', INCONCLUSIVE, reason='the result is not shown to apply to the target regime: ' + '; '.join(gaps), gaps=gaps)]
    return [method('structural', PASS, note='target regime lies inside the source regime on every declared axis')]


def run_mapping_declared(spec, check):
    if not check.get('mapping'):
        return [method('structural', INCONCLUSIVE, reason=f'no mapping is declared between {check["observable_a"]!r} and {check["observable_b"]!r}')]
    return [method('structural', PASS, mapping=check['mapping'])]


RUNNERS = {'evaluate': run_evaluate, 'equivalent': run_equivalent, 'integral': run_integral, 'derivative': run_derivative,
           'limit': run_limit, 'dimensional': run_dimensional, 'rate-interval': run_rate_interval, 'propagation': run_propagation,
           'resampling-unit': run_resampling_unit, 'fit-partition': run_fit_partition, 'assumption-declared': run_assumption_declared,
           'regime-match': run_regime_match, 'mapping-declared': run_mapping_declared}
FIELDS = {
    'evaluate': ({'expression', 'expected'}, {'variables', 'tolerance'}),
    'equivalent': ({'lhs', 'rhs'}, {'domain', 'points', 'seed', 'tolerance'}),
    'integral': ({'integrand', 'lower', 'upper'}, {'variable', 'params', 'expected', 'analytic', 'tolerance'}),
    'derivative': ({'function', 'expected'}, {'variable', 'params', 'domain', 'points', 'seed', 'tolerance'}),
    'limit': ({'expression', 'approaching', 'expected'}, {'variable', 'params', 'direction', 'tolerance'}),
    'dimensional': ({'expression', 'units'}, {'expected_unit'}),
    'rate-interval': ({'successes', 'trials'}, {'confidence', 'sides', 'claimed', 'tolerance'}),
    'propagation': ({'function', 'variables', 'claimed_sigma'}, {'correlations', 'seed', 'samples', 'tolerance'}),
    'resampling-unit': ({'resampled_unit', 'independent_unit'}, {'dependence'}),
    'fit-partition': ({'steps'}, {'evaluated_on'}),
    'assumption-declared': ({'required'}, set()),
    'regime-match': ({'source', 'target'}, set()),
    'mapping-declared': ({'observable_a', 'observable_b'}, {'mapping'}),
}
COMMON = {'id', 'kind', 'optional', 'require_methods', 'note', 'formulation'}


def validate_spec(spec):
    if not isinstance(spec, dict) or spec.get('verification_schema') != SCHEMA:
        raise VerificationError('SPEC_INVALID', 'verification_schema must be 1')
    allowed = {'verification_schema', 'verification_id', 'claim', 'assumptions', 'domain', 'inputs', 'source', 'checks',
               'tolerance', 'reviewer'}
    if set(spec) - allowed:
        raise VerificationError('SPEC_INVALID', 'unknown fields: ' + ', '.join(sorted(set(spec) - allowed)))
    claim = spec.get('claim')
    if not isinstance(claim, dict) or not isinstance(claim.get('id'), str) or not isinstance(claim.get('statement'), str) \
            or not claim['statement'].strip() or claim.get('consequence', 'routine') not in CONSEQUENCES:
        raise VerificationError('SPEC_INVALID', 'claim needs id, statement and consequence (routine or consequential)')
    if not isinstance(spec.get('verification_id'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', spec['verification_id']):
        raise VerificationError('SPEC_INVALID', 'verification_id is required (letters, digits, . _ -)')
    for a in spec.get('assumptions', []):
        if not isinstance(a, dict) or not isinstance(a.get('id'), str) or not isinstance(a.get('statement'), str):
            raise VerificationError('SPEC_INVALID', 'assumptions are {id, statement}')
    reviewer = spec.get('reviewer')
    if reviewer is not None and (not isinstance(reviewer, dict) or set(reviewer) - {'role', 'context_exposure', 'notes'}
                                 or not isinstance(reviewer.get('role'), str)
                                 or reviewer.get('context_exposure') not in ('bounded', 'qualified', 'full-history')):
        raise VerificationError('SPEC_INVALID', 'reviewer is {role, context_exposure: bounded|qualified|full-history, notes?}')
    checks = spec.get('checks', [])
    if not isinstance(checks, list) or len(checks) > MAX_CHECKS:
        raise VerificationError('SPEC_INVALID', f'checks must be a list of at most {MAX_CHECKS}')
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or check.get('kind') not in KINDS or not isinstance(check.get('id'), str) or check['id'] in seen:
            raise VerificationError('SPEC_INVALID', 'each check needs a unique id and a supported kind: ' + ', '.join(KINDS))
        seen.add(check['id'])
        required, optional_fields = FIELDS[check['kind']]
        keys = set(check) - COMMON
        if required - keys or keys - required - optional_fields:
            raise VerificationError('SPEC_INVALID', f"check {check['id']} ({check['kind']}): fields must be {sorted(required)} "
                                                    f"plus optional {sorted(optional_fields)}")
    return spec


def run_check(spec, check):
    head = {'id': check['id'], 'kind': check['kind'], 'required': not check.get('optional', False), 'note': check.get('note'),
            'formulation': check.get('formulation', 'primary')}
    try:
        methods = RUNNERS[check['kind']](spec, check)
    except (ExpressionError, VerificationError) as exc:
        return dict(head, status=ERROR, methods=[], error=str(exc), passing_families=[], not_run=[])
    except (KeyError, TypeError, AttributeError) as exc:
        return dict(head, status=ERROR, methods=[], error=f'malformed check: {type(exc).__name__}: {exc}', passing_families=[], not_run=[])
    return dict(head, status=settle(methods, check.get('require_methods', ())), methods=methods,
                passing_families=sorted({m['family'] for m in methods if m['status'] == PASS}),
                not_run=[m for m in methods if m['status'] == 'unavailable'])


def decide(spec, results):
    """Outcome rules. Nothing is upgraded: an unmet obligation lowers the outcome, a failed one invalidates it."""
    consequence = spec['claim'].get('consequence', 'routine')
    findings = []
    if not results:
        return 'not-checked', [{'severity': 'A', 'code': 'NO_OBLIGATIONS', 'message': 'the claim has no executable checks, so nothing was verified'}]
    failed = [r for r in results if r['status'] == FAIL]
    for r in failed:
        reason = next((m.get('reason') or ('; '.join(m['problems']) if m.get('problems') else None)
                       for m in r['methods'] if m['status'] == FAIL and (m.get('reason') or m.get('problems'))), None)
        findings.append({'severity': 'A', 'code': 'CHECK_FAILED', 'check': r['id'],
                         'message': f"{r['kind']} check failed" + (f': {reason}' if reason else '')})
    for r in results:
        for m in r.get('not_run', []):
            findings.append({'severity': 'D', 'code': 'TOOL_UNAVAILABLE', 'check': r['id'], 'message': f"{m['family']}: {m['reason']}"})
    if failed:
        return 'invalidated', findings
    pending = [r for r in results if r['required'] and r['status'] in (INCONCLUSIVE, ERROR)]
    for r in pending:
        why = r.get('error') or next((m.get('reason') for m in r['methods'] if m['status'] in (INCONCLUSIVE, ERROR) and m.get('reason')),
                                     'could not be established')
        findings.append({'severity': 'B', 'code': 'OBLIGATION_UNMET', 'check': r['id'], 'message': f"{r['kind']} check not established: {why}"})
    for r in results:
        if not r['required'] and r['status'] in (INCONCLUSIVE, ERROR):
            findings.append({'severity': 'D', 'code': 'OPTIONAL_UNMET', 'check': r['id'], 'message': f"optional {r['kind']} check not established"})
    passed = [r for r in results if r['status'] == PASS]
    if pending:
        return ('partially-verified' if passed else 'unresolved'), findings
    if not passed:
        return 'unresolved', findings
    classes = independent_classes(results)
    if consequence == 'consequential' and len(classes) < 2:
        findings.append({'severity': 'B', 'code': 'INDEPENDENCE_MISSING',
                         'message': f'a consequential claim needs two independent method classes; only {classes or "none"} passed '
                                    f'(supply a second formulation or a different method)'})
        return 'partially-verified', findings
    exposure = (spec.get('reviewer') or {}).get('context_exposure')
    if consequence == 'consequential' and exposure not in ('bounded', 'qualified'):
        findings.append({'severity': 'B', 'code': 'REVIEWER_NOT_INDEPENDENT',
                         'message': 'a reviewer who shared the author\'s full reasoning is not an independent check; declare '
                                    'reviewer.context_exposure as bounded (claim, source, scope) or qualified, and review from that'})
        return 'partially-verified', findings
    return 'verified-in-scope', findings


def independent_classes(results):
    """Distinct (method class, formulation) pairs that passed. The same formulation re-run in other arithmetic is one;
    a second formulation of the claim (closed form versus series, say) is another."""
    def label(r, f):
        cls = CLASS_OVERRIDE.get((r['kind'], f), CLASS[f])
        return cls if r.get('formulation', 'primary') == 'primary' else f"{cls}:{r['formulation']}"
    return sorted({label(r, f) for r in results if r['status'] == PASS and r['kind'] in QUANTITATIVE
                   for f in r.get('passing_families', []) if f in CLASS})


def scope_of(spec, results):
    domains = {}
    for check in spec.get('checks', []):
        try:
            if check['kind'] == 'equivalent':
                domains[check['id']] = domain_of(spec, check, names(parse(check['lhs'])) | names(parse(check['rhs'])))[0]
            elif check['kind'] == 'derivative':
                domains[check['id']] = domain_of(spec, check, {check.get('variable', 'x')})[0]
        except (ExpressionError, VerificationError, KeyError, TypeError):
            continue
    return {'statement': spec['claim']['statement'], 'assumptions': spec.get('assumptions', []), 'domain': domains,
            'tolerance': dict(DEFAULT_TOLERANCE, **(spec.get('tolerance') or {})),
            'defaulted_domains': sorted({v for r in results for m in r['methods'] for v in m.get('domain_defaulted', [])})}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def record_digest(record):
    body = {k: v for k, v in record.items() if k not in ('record_digest', 'created_at')}
    return hashlib.sha256(canonical(body).encode('utf-8')).hexdigest()


def clean(value):
    """JSON-safe: NaN/inf become strings so a record always serializes."""
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def require_context(spec, receipt):
    """A consequential claim must be reviewed with the project's context loaded, and the record says which."""
    if receipt is None and spec['claim'].get('consequence', 'routine') != 'consequential':
        return None
    try:
        import context_kernel as kernel
        kernel.require(receipt)
        if receipt['workflow'] not in CONTEXT_WORKFLOWS:
            raise kernel.ContextError('CONTEXT_WORKFLOW_MISMATCH', f"a {receipt['workflow']} receipt does not cover verification")
    except Exception as exc:
        code = getattr(exc, 'code', 'CONTEXT_REQUIRED')
        raise VerificationError(code, 'a consequential claim needs a fresh, usable context receipt from a review workflow'
                                if receipt is None else str(exc)) from None
    return {'receipt_id': receipt['receipt_id'], 'workflow': receipt['workflow'], 'outcome': receipt['outcome']}


def run(spec, *, receipt=None, now=None):
    """Execute every check in the spec and return a verification record. Writes nothing."""
    validate_spec(spec)
    context = require_context(spec, receipt)
    results = [run_check(spec, c) for c in spec.get('checks', [])]
    outcome, findings = decide(spec, results)
    record = {'verification_schema': SCHEMA, 'verification_id': spec['verification_id'], 'claim': spec['claim'], 'outcome': outcome,
              'scope': scope_of(spec, results), 'checks': clean(results), 'findings': findings,
              'independent_classes': independent_classes(results),
              'independent_families': sorted({f for r in results if r['status'] == PASS and r['kind'] in QUANTITATIVE
                                              for f in r.get('passing_families', [])}),
              'not_verified': [f['message'] for f in findings if f['code'] in ('OBLIGATION_UNMET', 'INDEPENDENCE_MISSING', 'NO_OBLIGATIONS')],
              'inputs': spec.get('inputs', {}), 'source': spec.get('source'), 'reviewer': spec.get('reviewer'), 'context': context,
              'environment': environment(), 'spec': spec,
              'created_at': now or datetime.now(timezone.utc).isoformat()}
    record['record_digest'] = record_digest(record)
    return record


def validate_record(record):
    if not isinstance(record, dict) or record.get('verification_schema') != SCHEMA or record.get('outcome') not in OUTCOMES:
        raise VerificationError('RECORD_INVALID', 'not a schema-1 verification record')
    if record.get('record_digest') != record_digest(record):
        raise VerificationError('RECORD_INVALID', 'record content does not match its digest (edited or corrupt)')
    validate_spec(record['spec'])
    return record


def rerun(record):
    """Re-execute the embedded spec. Reproducible when the outcome and every check status agree."""
    validate_record(record)
    spec = record['spec']
    results = [run_check(spec, c) for c in spec.get('checks', [])]
    outcome, _ = decide(spec, results)
    statuses, recorded = {r['id']: r['status'] for r in results}, {r['id']: r['status'] for r in record['checks']}
    return {'reproduced': outcome == record['outcome'] and statuses == recorded, 'outcome': outcome,
            'recorded_outcome': record['outcome'], 'check_statuses': statuses, 'recorded_statuses': recorded}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    runner = sub.add_parser('run', help='execute a verification spec and write a record')
    runner.add_argument('spec', type=Path)
    runner.add_argument('--out', type=Path, help='write the record here (never overwrites)')
    runner.add_argument('--receipt', type=Path, help='context receipt (required for consequential claims)')
    for name in ('validate', 'rerun'):
        sub.add_parser(name).add_argument('record', type=Path)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command == 'run':
            receipt = None
            if args.receipt:
                import context_kernel as kernel
                receipt = kernel.load(args.receipt)
            record = run(json.loads(args.spec.read_text(encoding='utf-8')), receipt=receipt)
            if args.out:
                if args.out.exists():
                    raise VerificationError('OUTPUT_EXISTS', 'refusing to overwrite an existing record')
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
            print(json.dumps({'outcome': record['outcome'], 'verification_id': record['verification_id'],
                              'findings': record['findings'], 'independent_classes': record['independent_classes'],
                              'record': str(args.out) if args.out else None}, indent=2))
            return 0 if record['outcome'] == 'verified-in-scope' else 1
        record = json.loads(args.record.read_text(encoding='utf-8'))
        if args.command == 'validate':
            validate_record(record)
            print(json.dumps({'valid': True, 'outcome': record['outcome']}))
            return 0
        report = rerun(record)
        print(json.dumps(report, indent=2))
        return 0 if report['reproduced'] else 1
    except (VerificationError, OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
