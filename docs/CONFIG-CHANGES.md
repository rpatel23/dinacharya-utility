# Changing habits.yaml: what each change does

This page covers how an edit to `habits.yaml` affects data you've already stored, past scores, and devices that haven't updated yet. Check it before changing an existing habit. Adding a new habit is always safe.

It's the outcome of spike #4 (Nov 2026). The decisions are at the end.

## How it works

- **Stored data knows only the habit id.** Each day stores `{n, t}` per id, with no kind, unit or threshold. What `n` *means* comes from the current config.
- **Every day is scored with the current config**, including past days. Changing a threshold or schedule therefore rescores history. Nothing you entered is lost, but past percentages can move.
- **The app never rewrites stored data.** A config change can make old values read differently, but only a tap rewrites a value, and only for the day you tap.
- **Values outside the current kind are read clamped.** A counter reads between 0 and `count`, and a number entry reads ≥ 0. Display, scoring and taps all use the clamped value; storage keeps the original (#6).
- **Config isn't synced.** Each device fetches `habits.yaml` when it opens (network first, falling back to the last valid copy). A device with a local override (**Habits…**) keeps using that until you choose **Use deployed**.

## Change matrix

Verdicts:
- **Free:** no effect on data or scores.
- **Rescores:** data is kept, and past scores change to match the new rule.
- **Read-rule:** old values are reinterpreted by a defined rule.
- **Split:** don't edit the existing id. Add `end:` to the old one and create a new id with `start:`.

| Change | Example | Verdict | What happens |
|---|---|---|---|
| Rename `name`, `note`, the min/max text of a check | — | **Free** | — |
| Move a habit between groups, reorder | — | **Free** | — |
| Counter `show: dots` ↔ `one` | greens | **Free** | — |
| Add a habit | `nsm` | **Free** | Starts empty |
| Remove a habit | — | **Free** | Hidden, not deleted. Re-adding the same id restores its history. |
| Rename the **id** | `sff` → `satfat` | **Split** | The new id starts empty, and the old one's history is hidden. Prefer changing `name`. |
| Change `min` / `max` numbers | water min 4 → 5 | **Rescores** | Past days are judged by the new threshold. To keep old scoring, split. |
| Add / remove `max` | greens (#3) | **Rescores** | Only the max count changes. Day % counts min, so it's unaffected. |
| Add / remove `max` text on a check | — | **Read-rule** | Without max text, any stored `n ≥ 1` reads as done (#3) |
| Raise `count` | water 6 → 8 | **Rescores** | Old values keep their unit count; the default min moves with `count` if `min` isn't written. |
| Lower `count` | water 6 → 4 | **Rescores** | Values above the new count read and show as full (`4/4`). Taps act on the shown value, like on any full counter. The stored value stays until you tap. |
| check → avoid | `sff`, `df` (#2) | **Read-rule** | `n > 0` reads as clean |
| avoid → check | — | **Read-rule** | Clean reads as done; failed (`-1`) reads as missed. Tapping a failed day sets done. |
| Any other kind change (check ↔ counter, check ↔ number, counter ↔ number, counter/number → avoid, avoid → counter/number) | water as a check → counter | **Split** | Old values are misread: a done check (2) reads as 2 of 6 units; 1 glass reads as clean; 3.5 mi reads as 4 partial units. The first tap overwrites the old value. |
| Change a number entry's `value` unit | mi → km | **Split** | Old numbers keep their old unit silently |
| `days`, `every`, `start`, `end` | yoga loses Tuesday | **Rescores** | Past days that become unscheduled drop out of the % (their data is hidden, not deleted). Newly scheduled past days count as missed. |
| Add / remove / change `per_week` | tonic 3-4 → 4-5 | **Rescores** | Every past week is re-judged. Adding it moves the habit out of Day % into Week %. |
| `week_start` | mon → sun | **Rescores** | Week grouping and `per_week` counts change for all history |
| Use a **new option** (one the app adds) | `avoid` | **Free once the app updates** | See "Devices on different versions" |

To keep old scoring when a habit changes, split it:

```yaml
water:   {name: Water, count: 6, min: 4, max: 6, end: 2026-11-30}
water2:  {name: Water, count: 8, min: 6, start: 2026-12-01}
```

## Devices on different versions

The app (through the service worker) and `habits.yaml` (through fetch) update separately. Usually the config arrives on the first open after a deploy, and the new app only on the open after that.

- **A new option reaching an old app** (e.g. `avoid` before #2 was installed): the old app rejects the whole file, keeps the last valid config and shows `Config error`. That fixes itself on the next open. No data is lost. **Accepted.**
- **New behaviour without a new option** (e.g. #3): old and new apps read the same values differently until they update. A tap on the old app can store a value the new app reads differently (e.g. a check tapped to 2), but every rule here keeps that readable. **Accepted.**
- **Avoid habits on an old app:** a failed day (`-1`) shows as missed, and a tap there clears it. That's a one-day window. **Accepted** (noted in #2).
- **Sync between devices using different configs:** a merge compares only `t`, never meaning. With one user and configs fetched on open, the window is a single session. **Accepted.**

Rule for changes: ship a new option in the **same commit** as the app code that understands it. The Pages workflow deploys both together, so they can never be split apart.

## Decisions (spike #4)

1. **Scoring the past: use the current config, plus split.** Effective-dated settings (`since:`) and freezing finished days were rejected. They add syntax, synced data and scoring complexity, all for a problem the `end:`/`start:` split already solves. History reflects what you entered; percentages follow the current rules.
2. **Kind changes: allow safe pairs, split the rest.**
   - Allowed in place: check ↔ avoid, adding or removing a check's max text, and changing a counter's `count`.
   - Every other kind change, and any unit change, needs a new id.
   - No data migrations: the "never rewrite stored data" rule stands.
3. **Guard rails: a non-blocking CI report.** The Pages workflow diffs `habits.yaml` against the last deployed version and lists risky changes in the run summary. It never blocks a deploy (#5).
4. **Unknown options: keep rejecting the file.** Ignoring an unknown option would be worse. An old app that ignored `avoid` would treat the habit as a plain check and let a tap overwrite a failure. Rejecting falls back to the last valid config, which is safe.
5. **Local overrides: leave as is.** The status bar already shows `Config: local`. No warning or expiry when the deployed file changes.
6. **Id renames: no alias key for now.** Change `name` instead. Revisit an `was:` alias only if an id ever has to change.

## Problems found

| Problem | Outcome |
|---|---|
| Lowering `count` shows e.g. `6/4`, and the first tap on a single-circle counter resets it to 0 | Fixed in #6: shows `4/4`; taps act on the shown value |
| A number entry shows a stored `-1` (e.g. after avoid → number) as "-1" in its box | Fixed in #6: shows blank and scores as missed |
| Kind changes outside the safe pairs misread old values, and the first tap overwrites them | Documented (split), flagged by CI (#5) |
| Threshold and schedule changes silently rescore history | Documented; flagged by CI (#5) |
| An old app rejects a config that uses a new option | Accepted; it fixes itself on the next open |
| Sync merges ignore config differences between devices | Accepted |
| A local override pins a device to an old config | Accepted (decision 5) |
