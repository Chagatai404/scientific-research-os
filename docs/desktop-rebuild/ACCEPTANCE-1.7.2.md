# Desktop 1.7.2 acceptance

Verified 2026-11-03 on Windows 11 Pro, branch `fix/security-1.7.2`.

## Security

- `ros serve` request smuggling: a refused request's unread body was read as a second request on the kept-alive connection. Refused
  requests and every POST now close the connection; chunked POST bodies are refused. Reported privately by Matt Abate.
- `ros serve` human acts: the page's session call handed out the cookie that approvals, decisions and waivers need. Pairing now comes only
  from the link `ros serve` prints (`/workspace/#pair=<token>`): the token is in the URL fragment, kept in that origin's storage and sent as
  `X-ROS-Pair`. No cookie is set, because browsers send cookies to every port of 127.0.0.1. Reported privately by Matt Abate.
- Claude Code's refused commands cover the option-first forms (`git -C . push`, `rm -fr`), `git config`, network tools and `gh api`.
- From an internal audit and an independent verification of the first fixes:
  - Files agents or documents wrote are served sandboxed, with script and page files as plain text; PDFs still open in the viewer.
  - No route or tool opens a network share (`\\server\share`, `\\?\UNC`, `\??\`, `GLOBALROOT`).
  - Other sites may link to the portal but not fetch from or frame it.
  - Jobs never import a module from their own folder (`PYTHONSAFEPATH`, and no empty `PYTHONPATH` entry).
  - The app's git reads switch off the clean/smudge filters and signature programs a repository's config names.
  - Office files are read at most 20 MB per part and 64 MB in all.

## Fixed

- #21: a message longer than half the model's context was dropped with everything else; the newest message is now always sent.
- #22: `.gitignore` lines anchored at the root (`/data/`) and folder lines deeper down (`build_output/`) hide what git hides.
- #23: two Ollama tool calls in separate stream frames stay two calls.

## Evidence

- Each security fix and each issue has a test that fails on the 1.7.1 code and passes now (`tests/test_ros_serve.py`,
  `tests/test_ros_local_safety.py`, `tests/test_ros_local_provider.py`, `tests/test_ros_operations.py`, `tests/test_ros_library.py`).
- All four browser journeys pass with the pairing link.

## Limits

- Pairing stops programs that reach the portal only over HTTP. A program or agent that can run commands as the person can start its own
  `ros serve` and read the link (`references/PORTAL.md`).
- `/source-media` is refused to other sites but open to local programs, as in 1.7.1.
- Updates are not code-signed; electron-updater checks only the sha512 in the release's own `latest.yml`. Signing needs a certificate.
- `desktop_installer_smoke.py` is not run on a computer with a Research OS install registered (it refuses to), and this one has one.
