# Competition notes: Scope Speedrun

Sources: the official site's documents (Getting Started, Agent interface, Reference agent, Rules, Prizes,
Leaderboard), the `arena --help` and `arena sets` output, and practice run t76c947ef88d4.
**Not yet read:** the kit's `AGENTS.md`, `docs/` (incl. `docs/shift.md`) and `reference-agent/` source. Read
those next and correct anything here that disagrees. Items marked *(observed)* come from looking at the practice
clinic, not from the docs.

## Task format
- A run works one **set**: a fixed queue of plain-text items at one clinic. Each item is a **message** or a **task**.
- The agent holds one item at a time. It can't look ahead or reopen a closed item.
- **Messages** state rules, workflows, facts or noise. Close them with `acknowledge`. Later tasks may depend on
  them, and a later message can change an earlier rule.
- **Tasks** ask for one answer. Close them with `answer` (string, number, or list of strings/numbers) or `skip`.

## Interface
- Env: `QUEUE_URL, SHIFT_SECONDS, SITE_URL, SITE_USERNAME, SITE_PASSWORD, LLM_BASE_URL, LLM_API_KEY, WORK_DIR`.
- `GET $QUEUE_URL/item` returns `{status, seconds_left, item:{id, kind, text}}`.
- `POST $QUEUE_URL/item/close` takes `{id, answer|skip|acknowledge}`. The response is the next state.
- Errors:
  - 409 `not_current`: body includes `state`.
  - 409 `ended`.
  - 400 `bad_request`, which includes JSON `true`/`false` as an answer.
  - 422 `wrong_action`.
  - 413 `too_large`.
  - 503 `unavailable`: the run fails on the organizers' side.
- The shift clock starts when the container starts. The shift ends on time out, queue finished, or container exit.
- Site: sign in at `$SITE_URL/login`. The session is a cookie. Drive it with a browser or send the same HTTP requests.

## Answer comparison (official)
- **Message-defined forms** are compared as text. Case, outer spaces, spaces next to `:`/`,` and repeated spaces
  are ignored. Everything else must match exactly: digits, leading/trailing zeros, `$`, hyphens, order.
  Send one string; a list is wrong.
- **Whole numbers:** must be bare and whole. A leading `$`, trailing `%`, sign and thousands commas are OK.
- **Amounts/decimals:** compared within a tolerance set by the question (half a cent for money).
- **Dates:** several formats are accepted. Slashes are read month first.
- **Date-times:** a time is the clock time in the zone the question names. A `Z` or offset is dropped, not converted.
- **Phone numbers:** 10 digits, or 11 starting with 1. Formatting is free.
- **Text** (name, username, ID, address): case and spacing are ignored. Punctuation and words count
  ("Smith, Jane" ≠ "Jane Smith", "St" ≠ "Street").
- **Lists:** a JSON list, or one string split on `,` `;` or newline. Order and repeats are ignored unless the question asks for an order.
- An empty string is wrong (−1). Use `skip`.

## Scoring
- Correct **+1**, wrong **−1**, skipped 0, not reached 0, message 0. Answer only if $P(\text{correct}) > 0.5$.
- A submission runs once on each scored set. Its score is the sum of the three.
- **The leaderboard shows each team's latest finished submission**, even if lower than an earlier one.
- The leaderboard freezes about a day before the end.
- **Final ranking** = latest submission's score + one run on a hidden final set (924 tasks, 60 min, $25 budget).
- **Ties:** more time left when the final set's queue finished, then fewer wrong answers.

## Sets and budgets (from `arena sets`)
| Set | Role | Length | Tasks | Model budget | Visibility |
|---|---|---|---|---|---|
| practice | practice | 20 min | 6 | $1 | items, expected answers, agent output |
| public | scored | 15 min | 224 | $8 | points and counts (docs: output via `arena logs`) |
| private-a | scored | 15 min | 226 | $8 | points and counts |
| private-b | scored | 30 min | 458 | $15 | points and counts |
| final | hidden | 60 min | 924 | $25 | nothing until the results |

- Practice: 30 runs/day, 2 at once. Submissions: 2/day, 1 in progress.
- About **4 s per task** of shift time ($\frac{900}{224}$, $\frac{1800}{458}$, $\frac{3600}{924}$).
- When the budget is spent, the endpoint returns 402 and the run continues.

## Model endpoint
- OpenAI-compatible proxy to OpenRouter at `LLM_BASE_URL` (ends in `/v1`).
- Routes: chat/completions, completions, embeddings, responses, models.
- Any OpenRouter model **except** web-search/browsing ones. Refused with 400 `policy_violation`: `:online`,
  `sonar`, `search-preview`, `deep-research`, `@preset/`, `plugins`/`web_search_options`, and web
  tools/URL content (only `data:` URLs).
- At most 32 concurrent requests. Each request ≤120 s.

## Sandbox
- 4 CPU, 8 GiB RAM, 1 GiB shm, 10 GiB disk in WORK_DIR, image ≤ 8 GiB.
- No internet: only the queue, the site and the model endpoint. Everything must be in the image.
- Image must be **linux/amd64** (`docker build --platform linux/amd64`).

## Rules (complete list from the Rules document)
1. Connect only to `QUEUE_URL`, `SITE_URL`, `LLM_BASE_URL`. No other network, directly or via a model/tool that
   reaches the web.
2. Don't access systems you weren't given (judge host, admin interfaces, other teams' things, competition source/config).
3. Don't crash or overload the site, judge, queue, endpoint or product. Heavy use of the product during your own run is OK.
4. One account and one team per person. "Anything not on this list is allowed."

## Reference agent (from its doc)
- Node + OpenCode session per task with headless Chromium. Uses `anthropic/claude-sonnet-5.5`.
- 150 s cap per task, re-signs in every task, and keeps only the messages between tasks.
- Scored 0 on practice (6 skipped). The doc says to keep a signed-in browser, reuse knowledge, and tune
  model/time first. Types live in `contracts/src/shiftProtocol.ts`.

## Wrenfield (observed, may differ per clinic version)
- Each page is a shell with a nested iframe (`/v/<random>/`). A script hashes the rendered layout before content
  shows, so plain HTTP scraping is impractical and a real browser is needed. Page loads take ~0.2–0.3 s.
- Navigation is URL-driven with GET query parameters (`/patients?lastName=`, `/billing?status=`…).
- Patient search is scoped to the working location: switch to **All locations** first.
- Some charts are restricted ("Restricted chart requests"); opening one asks for a reason (Providing care, Scheduling,
  Billing or insurance, Request from the patient, Other) and is recorded.
- *(observed Oct 6)* The working location, rows-per-page and list page number are server-side session state set by
  POST + reload. URL parameters such as `size=`/`page=` do nothing. On the hosted practice clinic these POSTs return
  503 (it is read-only), so the location stays Northgate there; on the judge's clinic they work.
- *(observed)* 10 locations (KS: Central time, CO: Mountain time). Patient search under one location hid patients of
  others, e.g. Jones search at Northgate: 87 results.
- *(observed)* Documents open in a nested viewer frame with "Download" -> a text PDF (fonts with ToUnicode) and a page image.
- *(observed)* Recurring series pages list "Changed dates" and "All dates" (each date with its status).
- *(observed)* Provider select has Active and Inactive groups (80 providers in practice); provider page shows the specialty.
- *(observed)* Practice clinic data differs from the data in a judge run (the practice run's patients are not in the
  hosted practice clinic), so expected answers can't be re-checked there; only the structure carries over.

## Task types seen in practice so far
- new_vs_established (rule from message 1)
- referral_source
- referral_reason (needs the letter's content)
- phone
- noise messages ("vending machine…")
