# Shared session runtime

`session.js` and `session.css` are the complete offline bundles. KaTeX 0.16.22
uses locally embedded WOFF2 fonts. Document fonts (Atkinson Hyperlegible Next and
Mono, Source Serif 4, and the blackboard's handwriting Kalam, Patrick Hand and Caveat; Fontsource 5.3.0, SIL OFL 1.1, see `FONTS-LICENSE.txt`) are
kept in `fonts/` and embedded the same way; `dependency-lock.json` lists their
hashes. After editing `theme.css` or `runtime.js`, run `python build.py --refresh`
to rebuild the bundles from the already verified KaTeX. `dependency-lock.json` records original
distribution file hashes and the official npm source; `KATEX-LICENSE.txt` retains
the license. Rebuild with `python build.py /path/to/extracted/katex/package`.
`runtime.js` and `theme.css` are editable Research OS sources.

`reader.js` is the native handout reader: safe inline DOM, responsive pagination,
source sections and explicit solution reveal. It stores only presentation checkpoints
through the existing session bridge. Rebuild with `python build.py --refresh` after
editing it or `stages.js`/`stages.css`; no external renderer or compiler is needed.

The document uses `main#ros-session` and semantic `data-ros` attributes listed in
`ResearchOS.VOCABULARY`. Question sections identify `data-question-id`; their
controls are generated from structured questions. Supported kinds: `mcq`, `multi`,
`numeric`, `matching`, `ordering`, `free-response`. Options are strings or
`{value,label}` objects. Answers are an option value or zero-based numeric index
for MCQ; an array for multiple selection/ordering; a key/value map for matching;
a finite number for numeric. Numeric tolerance is absolute; units are exact labels,
without implicit unit conversion. Free responses await the tutor's review.

Hints reveal progressively: only the next hint is offered. Submitting shows
"Checking…" until the response is checked: immediately after the save when the
question has an answer key, otherwise when the tutor records a review
(`question.reviews[]`: `response_event_id`, `verdict`, `feedback`, `reviewed_at`).
The verdict and the prepared explanation then appear together under the answer; a
`solution` event records that the explanation was shown. Confidence is a one-click 1–5 scale. These gates
support teaching, not secrecy: prepared answers are present in the session data.
Browser feedback never proves mastery or retained understanding. Session events
record response, hint, solution, confidence, checkpoint and open-question actions.
Canonical capability ledgers and existing human review remain authoritative.

Tutor presentation uses a native disclosure per question, open by default; nothing
collapses a question except the learner. Opening or closing changes only the view;
it does not emit evidence or impose a question-lock policy. Questions render where
their `<!-- ros-question: <id> -->` marker sits in the source, so the page follows
the session's order; questions without a marker follow the content.

Live updates: the host posts `{type:'update', state, body?}` after an external write.
The runtime keeps every unchanged top-level node (drafts, open panels, focus, scroll),
inserts only new or changed nodes and enhances them, renumbers questions and marks
arrivals. It posts `{type:'ready'}` once it can accept updates.

MCQ/multiple-selection rows have decorative letter badges; accessible input names
remain the authored option labels. Selected rows show prepared-criteria feedback
only after the check. Changing a draft clears its old correctness styling. Clear response resets
only the draft fields (and offers Undo clear until the draft changes), preserving saved attempts, hints, solutions and confidence.
It emits no reset event and does not decrement recorded-response progress.

The progress bar counts distinct questions with a response event, including pending
in-page attempts. It does not count correct answers, concepts learned, open questions,
confidence or hint events. Host save acknowledgement/failure remains in the existing
status line. Progress and disclosure state create no canonical state fields.

Generated section navigation preserves authored heading order and stable anchors,
omitting the repeated document title. At 1440px and wider, Contents occupies a
sticky margin rail; narrower panes use a keyboard-operable native disclosure.
Scroll position sets `aria-current="location"` on the active visible section.
Following a section link opens any authored ancestor disclosure, focuses the
heading, and closes narrow Contents. Navigation emits no learning event, changes
no canonical fields and uses no external navigation privileges. Without the
runtime, the generated native Contents disclosure remains open and usable.

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

The blackboard: `data-widget="board"` is a widget whose declaration carries a `script` (`board_schema: 1`, see `scripts/board_script.py` and
`references/HTML_SESSION_PROTOCOL.md`). `board.js` performs it on an always-dark chalk board (fixed colours, whatever the page theme); `board.css`
styles it. Writing uses Kalam by default (Kalam, Patrick Hand and Caveat are bundled, SIL OFL 1.1; a script may set `hand` to `kalam`, `patrick`,
`caveat`, `kalam-patrick` or `patrick-kalam`, the last two writing titles in one font and the rest in the other). Formulas are KaTeX, typeset in chalk
colours, not handwritten. The module is also a plain API (`ResearchOSBoard.mount`, `createPlayer`, `validate`, `silentSpeaker`, `deviceSpeaker`,
`audioSpeaker`); `mount` accepts extra `speakers` ({`speak(text, {index, id})` -> promise, `pause`, `resume`, `cancel`, `setRate`}), which is how a streamed
voice plugs in. **Recorded sentences** are `mount(..., {clips})`, `clips` being `{stepId: {url, seconds, pause}}`: `runtime.js` passes `state.board_audio[widgetId]`,
which `html_sessions.py` builds beside the page (a path relative to the page, or an embedded `data:` URL in a standalone export) only for steps whose sentence
still matches the one that was recorded. The recorded voice plays a step's clip, waits out the `pause` the delivery puts after the sentence, and says any step
without a clip, a clip that fails to play or one that stalls with the device voice or timed captions; it is the default voice only when every spoken step has a clip.
`board.js`, `board.css` and `runtime.js` are editable sources; run `python build.py --refresh` after changing any of them.

Approved locally bundled extensions may call
`ResearchOS.register('name', (element, {emit,renderMath}) => {...})` to enhance
`data-extension="name"` content. Extensions run inside the same iframe sandbox
and receive no filesystem, parent, Node or network privilege. Remote scripts and
arbitrary modules are not loaded. Extension failures retain a visible error.
Mobile behavior remains unverified; responsive CSS alone is not verification.

`stages.js` also provides a native Text lesson controller using the reader. It
consumes the existing prepared board steps (`say`, `do.write`, `do.math`) without
loading speech or drawing services, preserves lecture checkpoints when switching
presentations, and exposes missing diagram descriptions explicitly. The existing
Blackboard presentation remains available in the same three-column shell.

`advice.js` supplies Study advice in the existing staged shell. It consumes the
pure session-adaptation projection plus a bounded host-provided canonical snapshot.
Opening it, switching advice sources or paging never creates assessment evidence.
The dialog reuses the native reader; requests use ordinary open-question events.
