# Teaching resource protocol (v0.9.5)

Teaching can point to material other people made: a video, an interactive simulation, an article, a textbook chapter, a paper. This
protocol says how such a resource enters a lesson without the lesson trusting it blindly, loading it behind the learner's back, or
copying it. Evidence rules stay in `SOURCE_POLICY.md`; a resource supports teaching and is never itself evidence of a scientific claim.

## The registry

One file per resource, `<vault>/.research-os/resources/RES-<id>.resource.json` (`resource_schema: 1`), managed with
`python scripts/resources.py --vault <vault> …`. A record holds the title, https URL, kind (video, interactive, article, paper, textbook,
course, reference), publisher, **authority** (primary, textbook, university, educator, community, roughly in descending authority for the
claim shown), **language**, linked concept ids, licence and attribution, an optional YouTube embed and time segment, what the learner
should notice, who found it, and its status. Nothing is downloaded or copied; a record is a pointer plus what is known about it.

## States, forward only

| State | Means | Does not mean |
|---|---|---|
| `candidate` | someone found it | anything about quality |
| `checked` | the link resolved (`check` makes one HTTPS request, no cookies or credentials, size-capped, redirects must stay HTTPS) and the page identified itself; or a manual note with a date | that it is correct |
| `vetted` | someone watched or read the stated part against the source policy and recorded what they checked (at least 30 characters of basis), what the learner should notice, and the licence (`unknown` if unstated) | that it is right in every respect, or that it is free to copy |
| `rejected` | unsuitable, with a reason | |

Rules the tool enforces: a vetted record rests on a checked one; `vetted.by` starts with `agent: `, `reviewer: ` or `human: `; **a finder does
not vet their own find unless they are the human**; an `agent:` may vet only `routine` use, never material a claim the work depends on
(`consequential`), which needs a reviewer or the human. Only `vetted` and current records are reused. Vetting ages: after a year a record is
`stale` and offered for re-checking, because pages change and videos disappear.

## Language and authority

Prefer the learner's language when an equally authoritative resource exists in it (`reusable` sorts that way) and tag every resource with
its language. Authority is about the claim being shown: a primary paper or official documentation outranks a textbook, which outranks a
university course page, a reputable educator, and a community post. Names of channels or sites are examples of a category, not endorsements;
each use is checked on its own.

## How a lesson uses it

A Teaching Card lists up to six resources in `card.resources`, each a **snapshot** of a vetted record (`resources.py card <id>`), so the
session stays self-contained and works offline when the registry changes. The page shows a collapsed **Go further** list with kind, language,
publisher, licence, attribution and the host the link goes to. **Nothing loads until the learner clicks.**

* **Open** sends the learner to the resource in the system browser. In the Obsidian companion the page cannot hold a link (its sanitizer removes
  them and its sandbox forbids navigation), so it asks the host by resource id; the host looks the address up in state it holds, accepts only an
  HTTPS URL without credentials, and opens it. The page never supplies an address.
* **Play here** exists only for a vetted YouTube resource on a **standalone** page. The page's policy then allows exactly one frame origin,
  `https://www.youtube-nocookie.com`, the player is created on click inside a sandboxed frame, and the learner can close it. The Obsidian
  companion's policy is `frame-src 'none'` and stays so: embedding there would widen the security model of the whole session view and is a
  separate decision. Other embeds (including PhET simulations) are links only until their embed addresses are checked on the live site.
* Attribution that a licence requires is shown with the resource (PhET simulations are CC BY 4.0 and ask for an attribution line; the PhET name and
  logo are trademarks).

## What this does not verify

That a video explains the topic correctly (that is what vetting records, by a named person); that a licence permits what you do next (the record
copies what the page says; it is not legal advice); that a link still works tomorrow; that the Obsidian companion opens the browser on your machine
(tested against a stub host, not inside Obsidian); and that the YouTube player loads in a given environment.

## Commands

```
python scripts/resources.py --vault <vault> add --id RES-gamma-video --title "…" --url https://… --kind video --publisher "…" --authority educator --language en --concept gamma-density [--embed youtube --start 5 --end 120] [--found-by "agent: tutor"]
python scripts/resources.py --vault <vault> check RES-gamma-video            # online: resolves the link, records the page title
python scripts/resources.py --vault <vault> vet RES-gamma-video --by "human: <name>" --basis "Watched 0:05-2:00 against the gamma density in <source>; the shape parameter is stated correctly." --notice "…" --license "Standard YouTube licence"
python scripts/resources.py --vault <vault> list --concept gamma-density --lang tr --status vetted
python scripts/resources.py --vault <vault> card RES-gamma-video             # the snapshot to put in card.resources
python scripts/resources.py --vault <vault> index                            # a Markdown index; every row is a link
python scripts/resources.py --vault <vault> validate                         # exit 1 on a damaged record
```
