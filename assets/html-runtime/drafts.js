/* Unsent presentation state only. Draft identities never grade an answer or
   authenticate a message; the host owns session separation and persistence. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSDrafts = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  function canonical(value) {
    if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.keys(value).sort().filter(k => value[k] !== undefined).map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
    return JSON.stringify(value);
  }
  function signature(value) {
    const text = canonical(value), words = [2166136261, 2246822519, 3266489917, 668265263];
    for (let i = 0; i < text.length; i++) for (let j = 0; j < words.length; j++) words[j] = Math.imul(words[j] ^ text.charCodeAt(i), [16777619, 3266489917, 668265263, 374761393][j]) >>> 0;
    return words.map(w => w.toString(16).padStart(8, '0')).join('');
  }
  const validValue = value => typeof value === 'string' && value.length <= 4000;
  function key(tree, id) {
    if (!['probe', 'check'].includes(tree) || typeof id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(id)) throw new Error('Invalid prepared question draft identity');
    return 'answer:' + tree + ':' + id;
  }
  return {canonical, signature, validValue, key};
});
