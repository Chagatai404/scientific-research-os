# Teaching format: cards, word strips and lecture notes (v0.9.5)

A long paragraph with a formula and three unfamiliar words is a poor way to learn the idea behind it. This format puts the
idea first, defines words before they are used, shows one picture, and leaves a note you can recall from. The research it rests
on is summarized at the end; the checks are mechanical (`scripts/teaching_lint.py`) and cannot tell you the teaching is good.

## The Teaching Card

A teaching block (`html_sessions.py declare-block`) may carry a `card`:

```json
{"id": "density", "heading": "From the exponential to the gamma density", "kind": "derivation", "target": "gamma-density",
 "assumes": ["gamma-function"], "introduces": {"shape parameter": "The number of waiting stages."},
 "terms": ["shape parameter", "probability density"],
 "card": {"core_idea": "A gamma density describes the wait for several events, not just one.",
          "predict": "If you wait for three events instead of one, does the typical wait get longer or shorter?",
          "retrieve": "Say in your own words what the shape parameter counts.",
          "visual": "VIS-014-gamma-shape",
          "spoken": {"en": "Waiting for three events takes longer than waiting for one. The shape parameter counts how many events we wait for."}}}
```

| Field | Rule |
|---|---|
| `core_idea` | **Required.** The one idea of the section in words: at most two sentences and 40 words, no notation needed. |
| `predict` | Optional prompt shown before the section (concept, intuition and derivation blocks should have one). Viewing is never evidence. |
| `retrieve` | Optional prompt shown collapsed at the end of the section. |
| `visual` / `no_visual_reason` | The id of the figure or widget that carries the idea, or the reason there is none. Not both. |
| `spoken` | Language code → a script written to be heard: no notation, formulas said in words, under about 90 seconds. Narration reads this, never the formula text. |

A card is optional and per block. A block without one renders exactly as before, so existing sessions do not change. With one,
the page shows, under the heading and in this order: **In one idea**, **Predict first**, the **word strip**, then your prose; and a
collapsed **Check yourself** at the section end.

## The word strip

For every card block, the page builds a `glossary` callout from what the lesson can itself define:

* **New words in this section**: each term in the block's `introduces`, with its definition, open by default;
* **Words from earlier in this lesson**: terms listed in the block's `terms` that an earlier block introduced, collapsed.

A term is defined before it is used, in the learner's language. Whether the *learner* knows a term is a different question, answered
by the term ledger (`references/LEARNER_MODEL.md`) and enforced by the gate (`UNDEFINED_TERM`, `references/TUTORING_GATES.md`).
The strip is a projection; the stored lesson source is never changed.

## Layered lecture notes

`assets/obsidian/25_Lecture_Note.md` keeps the full lecture in the vault and makes it recallable at a glance:

| Layer | Holds | Why |
|---|---|---|
| **L0 Gist** | one sentence (at most 30 words), then "Words you need" as `- **term** — one line` | the whole idea and its vocabulary on one screen |
| **L1 Core in 60 seconds** | at least three collapsed `[!question]-` callouts, each with an answer | the first screen asks you to recall before it lets you reread |
| **L2 Lecture** | the full explanation: words, then the picture, then the formula | the lesson |
| **L3 Derivation and sources** | the derivation, assumptions, failure modes and at least one source | depth and provenance |

`python scripts/teaching_lint.py note <note.md>` checks the shape: the four layers once each and in order (an error), a short gist,
a words list, three or more collapsed questions with answers, a first screen under 400 words, a non-empty L2 and L3, a source in L3,
no unfilled placeholder. It does not read your mind: a note that lints clean can still teach badly.

## The lint

`python scripts/teaching_lint.py blocks --root <vault> <session> [--lang tr] [--require-spoken] [--strict]` reports, as warnings:
`CARD_MISSING`, `CORE_IDEA_LONG`, `PREDICT_MISSING`, `RETRIEVE_MISSING`, `NO_VISUAL`, `FORMULA_FIRST`, `FORMULA_DENSITY` (more than
three display formulas), `LONG_PARAGRAPH` (over 80 words), `TERM_BEFORE_INTRO` (a term used in a section before the one that
introduces it), `UNDECLARED_TERM` (a glossary term used but neither declared nor known to the learner), and for spoken scripts
`SPOKEN_MISSING`, `SPOKEN_LANGUAGE`, `SPOKEN_HAS_MATH`, `SPOKEN_LONG`. A malformed card is an error from the gate. The limits are
conventions to keep sections readable, not findings of research; change them in the script if they do not suit you.

## Why this shape

* Retrieval practice and distributed practice rate highest among common study techniques; rereading and summarizing rate low
  (Dunlosky et al. 2013, *Psychological Science in the Public Interest* 14(1)). Hence collapsed questions first.
* Multimedia learning (Mayer): introduce key terms before the complex material (pre-training), present in learner-paced segments,
  cut what does not serve the idea (coherence), and let narration carry what a diagram shows instead of repeating the same text
  on screen (redundancy). Hence the card, the word strip, the one visual and a separate spoken script.
* Scaffolding that helps novices can hurt experts (Kalyuga 2007, the expertise reversal effect): the word strip and prompts are
  most useful where the ledger says terms are unseen. Cards are optional for that reason.
* This is not matching to a learning style; no such matching is supported by evidence (Pashler et al. 2008).
