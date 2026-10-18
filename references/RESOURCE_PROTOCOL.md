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
  companion's session page keeps `frame-src 'none'`: nothing is framed inside the session view. A vetted video that a session **plan** names plays in a pane the
  host owns instead (next section). Other embeds (including PhET simulations) are links only until their embed addresses are checked on the live site.
* Attribution that a licence requires is shown with the resource (PhET simulations are CC BY 4.0 and ask for an attribution line; the PhET name and
  logo are trademarks).

## The video pane in Obsidian (decided 2026-10-18)

The researcher decided on 2026-10-18 to widen the Obsidian security model by exactly one thing: a **host-owned video pane** for a vetted YouTube record that the session's plan
plays. Before this, embedding in the companion was left as a separate decision. The reason: a session must never open an external browser, and a good existing video is faster
and better than a self-made animation (`SESSION_PLAN.md`, "Videos instead of drawing everything").

**What it permits.** One pane at a time, owned by the plugin (an Obsidian view of type `research-os-video`, opened in a split beside the session). It holds one frame, and the
host builds that frame's address itself: `https://www.youtube-nocookie.com/embed/<11-character id>?start=<s>&end=<e>&rel=0&autoplay=1&enablejsapi=1`. The frame is sandboxed
(`allow-scripts allow-same-origin allow-presentation`: no popups, no navigation of the pane, no forms, no modals), its referrer policy is `strict-origin-when-cross-origin`
(the player refuses to play with no referrer, error 153), and its permissions are encrypted media, picture-in-picture and fullscreen. `autoplay` follows the learner's own click on
"Play the video"; `enablejsapi` lets the pane hear the player say that it ended (the YouTube iframe API's `postMessage` handshake), and only messages from that frame's window
and the player's origin are heard. What the player says is reduced to ended, error code or ready; its words are never passed on.

**What the page can ask.** Only `{type:'video', action:'open', resource, start, end}` or `{action:'close'}`. The host accepts a request only if all of these hold:

1. `resource` looks like a registry id (`RES-…`), and a segment of **this session's own plan** has a `video` naming that id with exactly those `start` and `end` (the numbers
   used are the plan's, rounded to whole seconds, at most 30 minutes);
2. the session holds a snapshot of that record: `state.video_records[id]` (written by `html_sessions.py plan` from the vault registry, only for a record that is `vetted`,
   not stale, and `embed: youtube`) or a Teaching Card's `resources` entry; the snapshot is a card snapshot (`resources.py card`), so it carries the address and `vetted_on`;
3. the host checks the snapshot again: `embed` is `youtube`, the address is HTTPS without credentials on a YouTube host, `video_id` is 11 characters and equals the
   address's own, `vetted_on` is a real date no more than a year old;
4. requests are at most one per 0.4 s, and a new video replaces the old pane.

The page can **not** supply an address, a video id, a host name, a frame attribute, a registry path, or different times; any such field is ignored. It cannot reach a record that
the plan does not name, an unvetted or stale record, or anything that is not a YouTube video. The same pattern serves the handout: `{type:'handout', action:'open'}` opens a PDF
from `plan.handout.directory` (once `status` is `built`) in an Obsidian tab; a `path` the page names must be a `.pdf` inside that folder (not a sibling whose name only starts the
same, no `..`, scheme, drive, backslash, `%`, `#`, or hidden part), and with none the host takes the newest PDF there.

**What it does not widen.** The session page's policy is unchanged (`default-src 'none'`, `frame-src 'none'`, `connect-src 'none'`): nothing is framed or fetched by the page.
The pane is a separate Obsidian view, so a hostile page or module cannot script it, and the player's frame has another origin than Obsidian and no right to open windows or
navigate the pane. The system browser is never opened for a lesson's video, and not for the handout either.

**The remaining trust.** The agent that writes the plan, the registry and the session state is trusted as before; the worst a record that passes these checks can do is play a
different YouTube video than the vetting covered, which is what the vetting rules (a finder never vets their own find, `consequential` use needs a reviewer) are for. YouTube's
player is third-party code and contacts Google when it loads; that happens only after the learner presses "Play the video", through the `nocookie` host.

**When it fails.** The player can refuse (embedding disabled, error 150/153), the machine can be offline, the pane may not report the end. The page then says so and the lecture
goes on from the board and the handout; the video stays on offer ("Try the video again"). The learner can always say they have finished watching, and closing the tab counts as
finishing. A host that never answers is given ten seconds.

**Not verified.** Everything above is tested against a scripted Obsidian workspace (`tests/html-host.test.js`) and in headless Chrome against a scripted host
(`tests/html-stages-browser.cjs`); none of it has run inside Obsidian. Unknown until it does: whether YouTube's player loads in Obsidian's Electron frame at all (its `app://`
origin may be refused, error 153), whether autoplay is allowed, whether `getLeaf('split', 'vertical')` puts the pane where the lecture stays in view, whether the end-of-video
messages arrive, and whether Obsidian opens the handout PDF in its viewer.

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

### Integrated Video tab (2026-10-19)

The learner requested a course-player layout with a Video tab inside the session.
The session iframe still cannot embed or fetch. It names the same vetted resource
and planned interval, plus a finite, bounded player rectangle. The companion owns
an overlay only within that rectangle, leaving navigation and status visible; it
removes the player on tab exit or session reload. Legacy requests without a rectangle
retain the separate pane.

On desktop the integrated player is an isolated Electron guest with Node integration
disabled, context isolation and sandbox enabled, no preload or popups, and an
in-memory video partition. Its HTTP referrer identifies this application as
`https://md.obsidian.research-os-html`; it does not impersonate another site. The
host reads only the guest's media time, paused/ended flag and standard player error
for completion reporting. The evaluated expression is fixed plugin code, never
supplied by a session or remote player. Only the vetted YouTube embed address may
be navigated; no authentication or system browser is part of this flow.

This follows the documented [YouTube embedded-client identity requirement](https://developers.google.com/youtube/terms/required-minimum-functionality#embedded-player-api-client-identity)
and Electron's [guest referrer and isolation controls](https://www.electronjs.org/docs/latest/api/webview-tag).
Real Obsidian playback must still be verified independently of simulated host tests.


**Acceptance on 2026-10-19:** the vetted MIT MSE embed played in the actual Obsidian
Video tab. Slides and captions advanced, and the elapsed-time display progressed
from 0:05 to 1:06. The session navigation, player, return control and status all
remained visible. This supersedes the earlier unperformed-playback statement for
this one integrated desktop path; independent speaker recording and a physical
mobile device remain outside that evidence.
