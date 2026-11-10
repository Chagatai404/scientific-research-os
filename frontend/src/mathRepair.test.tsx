import assert from 'node:assert/strict';
import {test} from 'node:test';
import {repairMath} from './mathRepair';
import {legacyHandoutSyntax} from './documentSyntax';

// In these strings a JS escape (TAB, NEWLINE, FORM FEED, BACKSPACE) stands for a TeX backslash that a decoder ate;
// a doubled backslash is written explicitly.
test('a control character that ate the backslash of a TeX command is restored inside math', () => {
  assert.equal(repairMath('Let $\theta$, $\tau\nu$ and $a\times b$.'), 'Let $\\theta$, $\\tau\\nu$ and $a\\times b$.');
  assert.equal(repairMath('$$\nabla f = \text{grad}$$'), '$$\\nabla f = \\text{grad}$$');
  assert.equal(repairMath('$\frac{1}{2} \beta$'), '$\\frac{1}{2} \\beta$');
  assert.equal(repairMath('$a \neq b$'), '$a \\neq b$');
});
test('a newline then u is a variable in display math but \\nu inline', () => {
  assert.equal(repairMath('$\nu$'), '$\\nu$');
  assert.equal(repairMath('$$a =\nu + b$$'), '$$a =\nu + b$$');
});
test('doubled backslashes before a command collapse, but line breaks are kept', () => {
  assert.equal(repairMath('$\\\\frac{1}{2}$'), '$\\frac{1}{2}$');
  const aligned = '$$\\begin{aligned}a&=\\\\alpha \\\\ b\\end{aligned}$$';
  assert.equal(repairMath(aligned), aligned);
  assert.equal(repairMath('$$a \\\\ \\\\frac{1}{2}$$'), '$$a \\\\ \\\\frac{1}{2}$$');
  assert.equal(repairMath('$\\\\notacommand$'), '$\\\\notacommand$');
});
test('parenthesis and bracket delimiters become dollars', () => {
  assert.equal(repairMath('so \\(x^2\\) holds'), 'so $x^2$ holds');
  assert.equal(repairMath('\\[\\frac{a}{b}\\]'), '$$\\frac{a}{b}$$');
  const literal = 'see \\[1\\] and \\(see above\\) $x$';
  assert.equal(repairMath(literal), literal);
});
test('prose, currency and real newlines outside math are untouched', () => {
  const prose = 'It costs $5 and\nuseful things\ttab and $6 later.\nnabla here.';
  assert.equal(repairMath(prose), prose);
  assert.equal(repairMath('Costs $5, then $x\times y$ ok'), 'Costs $5, then $x\\times y$ ok');
  assert.equal(repairMath('a\nu $b$'), 'a\nu $b$');
  assert.equal(repairMath('no math\there'), 'no math\there');
});
test('an inline span cannot swallow prose across a newline that is not a command', () => {
  const text = 'price $5\nand then $7 more';
  assert.equal(repairMath(text), text);
});
test('code fences, indented code and inline code are never touched', () => {
  assert.equal(repairMath('```\n$a\times b$\n```\n$a\times b$'), '```\n$a\times b$\n```\n$a\\times b$');
  const tilde = '$x$\n~~~tex\n\\(x=1\\)\n~~~';
  assert.equal(repairMath(tilde), tilde);
  assert.equal(repairMath('use `$a\times b$` then $a\times b$'), 'use `$a\times b$` then $a\\times b$');
  assert.equal(repairMath('text\n\n    $a\times b$\n\n$a\times b$'), 'text\n\n    $a\times b$\n\n$a\\times b$');
});
test('escaped dollars and unmatched delimiters are left alone, and repair is idempotent', () => {
  assert.equal(repairMath('\\$a\times b\\$'), '\\$a\times b\\$');
  assert.equal(repairMath('lone $ sign\times'), 'lone $ sign\times');
  const once = repairMath('$\theta + \\\\alpha$ and \\(y\\)');
  assert.equal(once, '$\\theta + \\alpha$ and $y$');
  assert.equal(repairMath(once), once);
});
test('text without math returns the identical string, and the syntax adapter applies the repair', () => {
  const plain = 'nothing\there\nu';
  assert.equal(repairMath(plain), plain);
  assert.ok(legacyHandoutSyntax('Let $a\times b$').includes('$a\\times b$'));
});
