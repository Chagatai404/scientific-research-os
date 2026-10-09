# Shared session runtime

`session.js` and `session.css` are the complete offline bundles. KaTeX 0.16.22
uses locally embedded WOFF2 fonts. `dependency-lock.json` records original
distribution file hashes and the official npm source; `KATEX-LICENSE.txt` retains
the license. Rebuild with `python build.py /path/to/extracted/katex/package`.
`runtime.js` and `theme.css` are editable Research OS sources.

The document uses `main#ros-session` and semantic `data-ros` attributes listed in
`ResearchOS.VOCABULARY`. Question sections identify `data-question-id`; their
controls are generated from structured questions. Supported kinds: `mcq`, `multi`,
`numeric`, `matching`, `ordering`, `free-response`. Options are strings or
`{value,label}` objects. Answers are an option value or zero-based numeric index
for MCQ; an array for multiple selection/ordering; a key/value map for matching;
a finite number for numeric. Numeric tolerance is absolute; units are exact labels,
without implicit unit conversion. Free responses await human review.

Hints reveal progressively. Solutions require an attempted response. These gates
support teaching, not secrecy: prepared answers are present in the session data.
Browser feedback never proves mastery or retained understanding. Session events
record response, hint, solution, confidence, checkpoint and open-question actions.
Canonical capability ledgers and existing human review remain authoritative.

Math elements carry `data-tex` and optional `data-display="true"`. Unsupported
commands visibly preserve original TeX. KaTeX uses `trust:false` and bounded
expansion/size; its geometry needs iframe-local style attributes. Numbered
equations can use KaTeX `\tag{1}` and author-provided stable IDs for links.

The Obsidian host injects `window.ROS_HOST={token,session_id,state}` and authenticates
messages by frame/token/session. The runtime has no vault API. It sends
`{channel:'research-os',token,session_id,event}` and receives acknowledged state.
Save failures are visible. Reopening restores responses and revealed hints from
saved events. Standalone export reads JSON from `script#ros-session-data`; progress
exists only in the page until downloaded as JSON. It never uses localStorage.

Widgets: `data-ros="widget" data-widget="sampling"` demonstrates the analytic
standard-error formula for independent finite-variance observations; `vector`
demonstrates Euclidean vector components. SVG and Canvas are accompanied by
accessible numerical text and model limitations. These are neither validated
simulations nor experimental data.

Approved locally bundled extensions may call
`ResearchOS.register('name', (element, {emit,renderMath}) => {...})` to enhance
`data-extension="name"` content. Extensions run inside the same iframe sandbox
and receive no filesystem, parent, Node or network privilege. Remote scripts and
arbitrary modules are not loaded. Extension failures retain a visible error.
Mobile behavior remains unverified; responsive CSS alone is not verification.
