# Brief: design the live habits.yaml

This brief is for an AI agent (or a person) helping the owner design their real routine for **Daily Tracker**. The output is a `habits.yaml` that drops straight into the app. That work is tracked in issue #8.

Attach these files along with this brief:

| File | Why |
|---|---|
| [`docs/CONFIG.md`](CONFIG.md) | **The spec.** Every option, the habit kinds, scoring, YAML gotchas and validation errors. Anything not in it is rejected. |
| [`public/habits.yaml`](../public/habits.yaml) | The current test config, as a worked example. Its header comment summarises the options on one screen. |
| [`docs/CONFIG-CHANGES.md`](CONFIG-CHANGES.md) | Only if the owner keeps the test data: why ids must stay stable, and when to use a new id. |

## What the app is

A minimalist habit tracker in the style of a Windows 98 tool, used on a phone and other devices. Each habit gets a circle per day: **missed**, **min** (done) or **max** (extra credit). There's a Day view (groups of rows) and a Week view (a table with totals). Data syncs between devices. `habits.yaml` is the only place the routine is defined.

## How scoring works (design thresholds around this)

- **min means done.** It's the only thing **Day %** and **Week %** count. Set it to a realistic baseline the owner can hit on an ordinary day, not an aspiration.
- **max is optional extra credit.** It exists only where `max` is written, and never raises a percentage. Most habits should have no max. Give one only where a second, better level is genuinely worth tracking.
- **Kinds:**
  - **check** (one tap = done; with `max` text, two taps = extra);
  - **counter** (`count: N` units, `min`/`max` thresholds);
  - **number entry** (`value: unit`, e.g. miles);
  - **avoid** (`avoid: true`: starts blank, marked clean or failed). Use it for things being cut out (no social media, no sweets), not for "do X".
- **`per_week: N` or `N-M`** suits flexible habits (e.g. "3–4 times a week"). They count toward Week % only, not Day %, and the habit appears only on its `days`.
- **Schedules:** `days` (weekdays, weekend, `mon wed fri`…), `every: N` weeks with a `start`, and one active range per habit (`start` / `end`).

## Limits (don't work around them; list them as feature requests)

- **Screen:** it must fit a 360px phone. Keep names to **about 20 characters** and notes short (a few words), or they get truncated. Criteria text (min/max on a check) shows under the name, so keep it brief too.
- **Structure:** groups are the only sections, shown in the order written (e.g. Morning, Nutrition, Training, Work, Evening). Habits within a group also keep their order.
- **Not supported:** reminders, times of day, timers, monthly or "nth weekday" schedules, different thresholds on different days, per-habit notes (notes are per day), and habits that depend on other habits.
- **Ranges:** a counter has at most 20 units. A number entry is one number with a unit. `per_week` is 1–7.
- **YAML 1.2:** `yes`/`no`/`on`/`off` are plain text. Quote text containing a comma, a `: ` or a ` #`. Indent with spaces.

## Ids

- An id is the key the history is stored under. Make it **short, lowercase and meaningful** (`water`, `deep`, `nsm`), and **unique across all groups**.
- Once tracking starts, an id never changes. Rename with `name` instead, and change kind or unit only by adding a new id (CONFIG-CHANGES.md).
- If the owner keeps the test data (decision 1 below), reusing a current id means inheriting its test history. Only reuse one when the habit means exactly the same thing.

## Questions for the owner

Answer these before drafting. Ask the owner for anything missing rather than guessing.

1. **Test data:** start fresh (suggested), or keep the history under unchanged ids?
2. **Start date:** the first real tracked day.
3. **The week:** work hours, training plan by day, busy days, and what changes at weekends.
4. **Goals:** what matters most now, and what's nice to have. (Fewer habits that are actually done beat a long list.)
5. **Units:** glass or cup size, run distances, what counts as a session (e.g. "deep work = 1 hr").
6. **Date ranges:** anything that starts later or stops on a date (a programme, a procedure, travel).
7. **Avoid list:** things being cut out (currently `sff` saturated fat, `df` distraction-free, `nsm` no social media).
8. **Two-level habits:** which habits have a real "extra" level worth a max (currently Voice, Processed-carb free, Deep work, Water, Screen breaks).
9. **Flexible habits:** which are "N times a week" rather than fixed days.

The current test routine (`public/habits.yaml`) covers:
- morning eye/voice practice;
- an Ayurvedic evening routine;
- nutrition;
- training Mon–Sun;
- work and study blocks.

Its thresholds were guesses: water 4 of 6 (max 6), greens 3 of 4, screen breaks 2 of 3 (max 3), and the LinkedIn post start date. Treat it as a starting point to confirm or replace, not as requirements.

## Deliverables

1. **One `habits.yaml`**, valid against CONFIG.md, with the header comment kept or updated.
2. **A table:** id · name · group · kind · schedule · threshold, plus one line on *why* (especially for min/max values).
3. **Open questions** for the owner, kept separate from the file.
4. **Feature requests**: anything the routine needs that the app can't do, kept separate. Don't encode it with workarounds.

## Before handing back

- **Try it:** paste it into the app's **Habits…** editor. It must load with no `Config error`. The status bar then shows `Config: local`, and **Use deployed** undoes it.
- **Check the fit:** look at the Day view on a phone. Names shouldn't be cut off, and each group should fit on one screen if possible.
- **Hand it back:** give the file to the repo (issue #8). The repo checks it, runs the change report (`tools/config_diff.py`), deploys it and handles the data reset.
