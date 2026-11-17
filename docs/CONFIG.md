# habits.yaml reference

`habits.yaml` defines every habit the tracker shows: what it's called, which days it appears, and what counts as done (**min**) and, optionally, extra credit (**max**). Each change you make there applies on every device. Deployment is covered in `DEPLOYMENT.md`, section 1.4.

## Structure

```yaml
week_start: mon            # first day of the week view and of per_week counting (default mon)

groups:                    # shown in this order
  Nutrition:               # group name = section title
    sff:   Saturated-fat free                              # short form
    water: {name: Water, note: 12 oz, count: 6, min: 4}    # full form
```

- **`groups`** maps group names to habits. Groups and habits appear in the order you write them.
- **Each habit** is `id: …`. The **id** is the key your history is stored under. Keep it stable, short, and unique across all groups.
- **The short form** `id: Name` is a daily check.
- **The full form** `id: {name: …, options}` uses the options below. You can also write it as an indented block instead of `{ }`.

## Options

| Option | Value | Default | Meaning |
|---|---|---|---|
| `name` | text | the id | Label shown in the app. Safe to rename. |
| `note` | text | — | Short hint shown in grey beside the name. |
| `days` | `mon tue …`, `weekdays`, `weekend`, `daily` | `daily` | The weekdays the habit appears. Separate days with spaces or commas, or write them as a YAML list. |
| `every` | whole number ≥ 1 | `1` | Appears every N weeks on its `days`. Needs `start`. |
| `start` | `YYYY-MM-DD` | — | First day the habit appears. Also the reference week for `every`. |
| `end` | `YYYY-MM-DD` | — | Last day the habit appears. |
| `per_week` | `N` or `N-M` (1–7) | — | A flexible weekly target, scored once a week instead of daily (see Scoring). |
| `count` | 1–20 | — | Makes the habit a **counter** with that many units. |
| `show` | `dots`, `one` | `dots` | How a counter is drawn: `dots` is one circle per unit. `one` is a single circle showing a number; tap to add 1, right-click to subtract 1. |
| `value` | unit text, e.g. `mi` | — | Makes the habit a **number entry** in that unit. |
| `avoid` | `true` / `false` | `false` | Makes the habit an **avoid** habit: something you try not to do (see Habit kinds). Can't be combined with `count`, `value`, `show`, `min` or `max`. |
| `min` | number or text | see below | The **min** criterion: what counts as done. |
| `max` | number or text | — | Optional **extra credit**. A habit has a max level only when you write `max`. |

Any option not in this table is rejected, so a typo like `cnt:` gives an error instead of being silently ignored.

## Habit kinds

**min** means done, and it's what Day % and Week % measure. **max** is optional extra credit beyond that, and exists only when you write it. Most habits need neither: a plain check is done or not done.

What `min`/`max` mean depends on the kind of habit:

| Kind | Declared by | What you enter | `min` / `max` |
|---|---|---|---|
| **check** | no `count`, `value` or `avoid` | One circle. Without `max`, a tap toggles missed ↔ done (min). With `max`, it cycles missed → min → max. | **Text** describing each level, shown under the name. Both optional; `max` text adds the extra-credit level. |
| **counter** | `count: N` | 0…N units | **Numbers** (thresholds). `min` defaults to `count`. There's no max unless you write one. `max` needs `min` and can't be greater than `count`. |
| **number entry** | `value: unit` | Any number ≥ 0 | **Numbers** (thresholds). With neither set, the habit is **logged only** and not scored. `min` alone means done at that value, with no extra credit. `max` needs `min`. |
| **avoid** | `avoid: true` | One circle that cycles blank → clean (green) → failed (red) → blank | Not allowed. It's pass/fail: clean counts as **min** and never as max. |

```yaml
nsm:    {name: No social media, avoid: true}        # blank until you mark it: clean or failed
```

Use **avoid** for things you're trying not to do. Leave it blank until you know how the day went. Mark it **failed** (red) when you slipped, which records the slip instead of looking like you forgot to log it. A check is the better fit when "avoiding" has two levels, such as `pcf` (no refined carbs / also no sugar).

The same habit can be written several ways depending on how you want to enter it:

```yaml
water:  {name: Water, count: 5, min: 3}             # 5 circles; done at 3, no extra credit
water:  {name: Water, count: 5, min: 3, max: 5}     # done at 3, extra credit at 5
water:  {name: Water, count: 5, min: 3, show: one}  # 1 circle, tap up to 5
water:  {name: Water, value: glasses, min: 3, max: 5}
water:  {name: Water, min: 3 glasses, max: 5 glasses}  # check: you judge the level yourself
water:  {name: Water, note: 3+ glasses}             # check: done or not
```

## Scoring

Each habit gets a level for each day:

| Level | check | counter / number entry | avoid |
|---|---|---|---|
| **max** (only if `max` is set) | You tapped it twice | value ≥ `max` | — |
| **min** | You tapped it once | value ≥ `min` | clean (green) |
| partial | — | 0 < value < `min` (shown pale, counts as missed) | — |
| missed | not tapped | 0 | blank, or failed (red) |

- **Day %** is the share of that day's scored habits that reached at least min. The bar also shows how many reached max, when any of that day's habits has one. Extra credit never raises the percentage.
- **`per_week` habits** don't count toward the day. A day counts toward the weekly target when it reaches at least min. The week counts as min once that reaches `N`, and as max once it reaches `M`. These habits still appear only on their `days`.
- **Week %** combines every scored day in the week with each `per_week` habit counted once.
- Levels are calculated from what you entered whenever they're displayed. Changing `min`/`max` therefore changes how past days score too. To keep the old scoring for the past, see Changing habits safely.

## Schedules

```yaml
yoga:     {name: Yoga, days: mon tue thu fri}
deep:     {name: Deep work, days: weekdays}
long:     {name: Long run, days: [sun]}
linkedin: {name: LinkedIn post, days: sun, every: 2, start: 2026-11-22}     # every other Sunday
tonic:    {name: Carrot–amla tonic, days: weekdays, per_week: 3-4}          # any 3–4 weekdays
sweets:   {name: No sweets, avoid: true, per_week: 5}                       # clean on at least 5 days
eyewash:  {name: Eye wash, end: 2026-12-01}                                 # stop, e.g. before surgery
```

- Day names are matched on their first three letters, so `Monday`, `mon` and `MON` are all the same.
- `every: 2` counts whole weeks starting from the week that contains `start` (using `week_start`), and the habit appears only in alternate weeks.
- Each habit has one active range. To pause a habit and resume it later, remove or move its `end` when you resume. The id stays the same, so its history continues.

## Changing habits safely

| You want to | Do this | Effect on history |
|---|---|---|
| Rename | Change `name` | Kept |
| Move to another group | Move the line | Kept |
| Retire | Delete the line | Hidden, not deleted. Re-adding the id restores it. |
| Change thresholds from now on only | Add `end:` to the old habit and create a new id with `start:` | Old days keep their old scoring |
| Start over | Use a new id | Starts empty |
| Turn a check into an avoid habit | Add `avoid: true` (and remove `min`/`max`) | Kept: past taps at min or max read as clean |

## YAML gotchas

The app parses YAML 1.2, so `yes`, `no`, `on` and `off` are plain text, and dates stay as text.

- **Commas inside `{ }`** separate options, so quote any text containing a comma:
  `note: "wide-tooth, dry hair"`
- **Colon followed by a space** inside text needs quotes: `note: "AM: smoothie"`. Times like `1:30–3:30` are fine either way, but quoting them is safest.
- **`#`** after a space starts a comment. Quote it if you need it in text: `note: "set #2"`.
- **Indentation** uses spaces, not tabs. In the app's editor, the Tab key inserts two spaces.

## Validation errors

The app checks the whole file before using it. Each error names the habit:

| Message | Fix |
|---|---|
| `x: unknown option "cnt"` | Check the spelling against the Options table |
| `x: unknown day "tu"` | Use at least the first three letters (`mon`…`sun`), `weekdays`, `weekend` or `daily` |
| `x: min > max` | Lower `min` or raise `max` |
| `x: max > count` | `max` can't be more units than the habit has |
| `x: min > count` | `min` can't be more units than the habit has |
| `x: max needs min` | A counter or number entry with `max` also needs `min` (what counts as done) |
| `x: every needs a start date` | Add `start: YYYY-MM-DD` |
| `x: use count or value, not both` | Pick one kind |
| `x: show needs count` | `show` only applies to counters |
| `x: avoid habits are pass/fail; remove min` | Avoid habits take no `count`, `value`, `show`, `min` or `max` |
| `x: avoid is true or false` | Write `avoid: true` |
| `Duplicate id "x"` | Ids must be unique across all groups |
| `Missing top-level "groups:"` | The file must have a `groups:` key |

If the deployed file is invalid, the app keeps using the last valid version and shows the error in the status bar.
