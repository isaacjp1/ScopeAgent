# Speedrun agent v5: architecture

## Why v4 ran over time
- **The Dockerfile overrode the time policy.** `ENV TASK_SECONDS=40`, `MAX_TURNS=25` and `TIME_STRETCH=3` won over
  config.py, so a hard task could take 12 s or more against a budget of about 4 s per task (900 s / 224 tasks).
- **Every task went through the model loop.** Find the patient, call a tool, submit: 3 to 5 model turns of about
  1 s each, every one carrying a prompt of over 5k tokens. That is the 4 s budget gone before any page loads.
- **Every message went into every prompt.** On the 924-task final set, messages pile up and every turn gets slower
  and more expensive.
- **Every phone task took a screenshot and made a vision call** (2–3 s), even after the digit scramble had been learned.

The queue gives one item at a time, so tasks can't run in parallel. Speed has to come from fewer model turns per task.

## Component decisions

| Component | Options weighed | Chosen | Why |
|---|---|---|---|
| Queue controller | sequential / prefetch next item | Sequential (the API allows nothing else). Messages are acknowledged at once; the rule compile runs in the background | One item at a time is a protocol rule |
| Wrenfield access | raw HTTP / Playwright DOM / screenshots + vision | Playwright DOM extraction (kept from v4). Pages are cached by path. Vision is used only for phone digits | The layout-hash check blocks raw HTTP, and vision is slow and costly |
| Task routing | LLM router / regex / embeddings | **Regex, with the records as the check.** A name only counts if the records have it, e.g. the provider is in the directory, or the patient's DOB and both names match | Costs 0 s and 0 model calls. When anything is unclear the general model loop takes over, so nothing is lost |
| Answer logic | model reasons / deterministic code | **Code** for known kinds (new/established, phone, documents). The model loop handles everything else | Code gives the same answer every time and needs no model turns |
| Rules memory | all messages in the prompt / summaries / compiled rules | Messages are stored word for word. When they exceed 16k characters, those sharing the most words with the task are kept. The N/E rule is **compiled to parameters and checked against the message text** | A summary could drop an exact answer format. The compiled rule is used only after every value in it is found in the message text |
| Model orchestration | one model / per-role models | One fast model, reasoning effort low, with a short prompt per role: compile the rule, extract from a document, read a phone screenshot, run the general loop | The calls are small and a second model adds risk. Override with `MODEL` |
| Time/budget | fixed cap / fair share / expected value | Fair share × 2.5, clamped to 4–20 s. Kinds of task the loop has never answered are skipped at once when time is short. The loop stops at 90 % of the set's budget | Skip and not reached both score 0, so slow skips steal time from tasks that could be answered |

## Data flow
```
queue item ──message──▶ Rules.add (ack now) ─bg─▶ compile+check N/E rule
          └─task──▶ Fast.solve ──regex kind──▶ pick_patient (DOB search, both names, one active chart)
                       │                        ├─ N/E: provider in directory → appointment_history → rule → answer
                       │                        ├─ phone: chart → learned digit map / screenshot+vision cross-check
                       │                        └─ document: docs tab → one row on that date → PDF text → model extracts
                       │                                                         → answer must appear word for word in the document
                       └─None──▶ model tool loop (relevant messages, route hints, prefetch, ≤10 turns, deadline)
                                     → shape check (phone digits, "how many" = number) → answer | skip
```

## Deterministic code vs LLM
- **Code:** finding patients, resolving merged and restricted charts, paging, time zones, the 3-year window,
  specialties, the N/E decision, answer templates, phone digit decoding, every validation, and time and budget.
- **LLM:** flagging chatter, turning rule text into parameters (checked afterwards), pulling an answer out of a
  document (checked word for word), reading a phone off a screenshot (checked against the digit substitution), and
  the general loop for unknown kinds.

## Memory and state
| Kind | Where | Lifetime |
|---|---|---|
| Shift rules/messages | `Rules.items` (verbatim), `Rules.ne` (checked parameters, the newest version wins) | whole shift |
| Facts from Wrenfield | `Site.cache` (path → page), `specialty_cache`, `providers`, `digit_map` | whole shift (the data is read-only) |
| Navigation knowledge | `notes.md` in the prompt and `nav_links` | static plus learned |
| Task state | the loop's conversation and `opened_text` | one task |
| Reusable patterns | `Memory.items` (the routes that answered similar tasks, given to the loop as hints) and `Memory.outcomes` (kinds that were never answered) | whole shift |

## Error recovery
- Any surprise in a fast path → `None` → the model loop takes over with every page it read already cached.
- Model errors: 4 retries with backoff, and the `reasoning` field is dropped if a model rejects it.
  A 402 stops all model calls, but N/E tasks still get answered without the model.
- Queue: a 400 on an answer becomes a skip, a 409 carries the next state, and network errors are retried.
- Uncertain cases are skipped: confidence < 0.7, a failed shape check, an unsafe tool result, a restricted chart,
  an incomplete list, or a location switch that wasn't confirmed.

## Time and budget allocation
- Cap = clamp(2.5 × seconds left ÷ tasks left, 4, 20). Fast paths take about 1–2 s, so the time they save goes to
  harder tasks later.
- If the fair share drops below 6 s, a task like 3 or more earlier loop tasks that were all skipped is skipped at once.
- Budgets per set ($1, $8, $15, $25) are known from the shift length. The loop stops at 90 % so the cheap calls
  still work.

## Highest-impact next steps (in order)
1. Run practice and check `[fast]` against `loop`, and the `[rules] ... OK` line. Every task kind that shows up
   often in the logs should get its own fast path, written the same way (regex → checked against the records → code).
2. Log the kinds of task in the scored sets (`arena logs`) and add fast paths for the 3–5 most common
   (billing balances, appointment counts, the provider for a date).
3. Speed up page loads: lower the `_wait_content` quiet thresholds after measuring on the real site.
4. Phone without vision: compare canvas renderings of the scrambled font against the body font.

## Phases
1. **Done (v5):** fast paths for N/E, phone and documents; compiled rules; chatter filtered from prompts; time
   and budget policy; Dockerfile fixed.
2. More fast paths, driven by the logs of scored sets.
3. Tune page waits and the number of tabs on the real clinic, and phone decoding with no vision call.
4. Lower the per-kind confidence threshold where the logs show answers are reliably right.

## v7: fixes from practice run t6d60cc954d3e
In that run no fast path fired. Each fix below targets a failure in its log:
- **Thinking tokens.** Gemini 3.8 Flash spends max_tokens on thinking. With caps of 300–600 the rule compile and
  the phone read came back empty, so every call now gets 3–4k. A reply with `finish_reason=length` is never used:
  it is retried once, then the task falls back.
- **429 concurrency_limit.** The proxy allows fewer requests in flight as the budget shrinks (1 at $1 left).
  `LLM` keeps a slot limiter that follows the number given in the 429 message. The chatter classifier, a
  needless extra call, is gone.
- **Slow model turns (1.5–5.9 s).** Reasoning effort is now `low` by default. The loop submits a safe
  `new_or_established` result at once instead of re-checking providers (that re-checking ran out the clock on one task).
- **Documents with no PDF text.** "Which practice" is read from the document title in the list (about 0.5 s; confirmed
  on the real site by the v6 run). Content questions fall back to a screenshot: the model must transcribe the page,
  and its answer must appear in that transcription and be at least 2 words.
- **Diagnosis.** Every fast-path fallback prints `[fast] fallback to the model loop: <why>`, and an empty PDF
  download prints its size and first bytes.
