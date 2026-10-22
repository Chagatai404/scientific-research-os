# Portal

`ros serve` serves one page per record at `http://127.0.0.1:8737/`, opened in a browser or Obsidian's core Web
Viewer. The process is the record's single writer while it runs.

| Section | Contents |
|---|---|
| Today | Reviews due (Review now), the next lesson (ready, or what is missing), answers waiting for the tutor, and a small closed **Context** window: how this record is linked, its research and what you know of what it needs |
| Learn | A **Roadmap** card (the next five steps with why and Start; in a project record, where to study them), prepared lessons, the capability map (click a node for its state and questions), the lesson player |
| Research | The decision queue (approve, decide), the claims ledger with verdicts and ownership |
| Library | Lesson logs |
| History | Every answer and its grade |

## Rules

- One column on phones; on desktop a 240 px rail and a 72-character column. No floating tool rail, no dialogs.
- One type scale, an 8 px grid, one button component at least 44 px tall.
- No text overlap or overflow from 320 to 1920 px (checked by `tests/ros-portal-browser.cjs`).
- At most six learner controls in a lesson.
- Our code at most 60 KB of JS and 20 KB of CSS; KaTeX and fonts are vendored, cached files.
- Loopback only; foreign Host headers are refused; writes need the `X-ROS` header; media only from `bundles/` and
  `logs/`; nothing is loaded from the network.

The same operations exist as `ros` commands and MCP tools; the page adds nothing an agent cannot do except the
person-only acts (approve, decide, waive).
