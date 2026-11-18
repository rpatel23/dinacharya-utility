"""Report risky changes between two versions of habits.yaml (issue #5, docs/CONFIG-CHANGES.md).

    python tools/config_diff.py OLD.yaml NEW.yaml [--base SHA] [--head SHA]

Prints a Markdown report. It is informational only and always exits 0; CI appends it to the run summary.
Free changes (name, note, group moves, `show`, check criteria text) are not listed. If the habits are
identical, nothing is printed.
"""
import argparse
import pathlib
import re
import sys

import yaml


class CoreLoader(yaml.SafeLoader):
    """SafeLoader with YAML 1.2 core-schema scalars, like the app's jsyaml.CORE_SCHEMA:
    only true/false are booleans (yes/no/on/off stay text), no sexagesimal numbers, dates stay text."""


CoreLoader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:int",
                                                     "tag:yaml.org,2002:float", "tag:yaml.org,2002:timestamp")]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
CoreLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))
CoreLoader.add_implicit_resolver("tag:yaml.org,2002:int", re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$"), list("-+0123456789"))
CoreLoader.add_implicit_resolver("tag:yaml.org,2002:float", re.compile(
    r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"), list("-+0123456789."))

DN = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
KIND = {"check": "check", "avoid": "avoid", "count": "counter", "value": "number entry"}
SAFE_KIND = {frozenset(("check", "avoid"))}          # kind changes allowed in place (CONFIG-CHANGES.md)
DOC = "docs/CONFIG-CHANGES.md"


def days(v):
    """Weekday numbers a habit appears on, following parseDays() in index.html. None = daily."""
    if v is None or v == "daily":
        return frozenset(range(7))
    out = set()
    for t in (v if isinstance(v, list) else re.split(r"[\s,]+", str(v))):
        t = str(t).lower()
        if not t:
            continue
        if t == "weekdays":
            out |= {1, 2, 3, 4, 5}
        elif t in ("weekend", "weekends"):
            out |= {0, 6}
        elif t == "daily":
            out |= set(range(7))
        elif t[:3] in DN:
            out.add(DN[t[:3]])
        else:
            out.add(t)                                   # invalid; compare as-is
    return frozenset(out)


def fmt_days(s):
    if s == frozenset(range(7)):
        return "daily"
    names = [k for k, n in sorted(DN.items(), key=lambda x: (x[1] - 1) % 7) if n in s]
    return " ".join(names + sorted(str(x) for x in s if not isinstance(x, int)))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def habit(raw):
    """The fields that matter for history, from one habit entry (following compile() in index.html)."""
    h = raw if isinstance(raw, dict) else {"name": raw}
    kind = "avoid" if h.get("avoid") is True else "count" if h.get("count") is not None else \
           "value" if h.get("value") is not None else "check"
    f = {"kind": kind, "group": None,
         "days": days(h.get("days")), "every": h.get("every", 1), "start": h.get("start"), "end": h.get("end"),
         "per_week": str(h.get("per_week")).replace(" ", "") if h.get("per_week") is not None else None}
    if kind == "count":
        f["count"] = num(h.get("count"))
        f["max"] = num(h.get("max"))
        f["min"] = num(h.get("min")) if h.get("min") is not None else (None if h.get("max") is not None else f["count"])
    elif kind == "value":
        f["unit"] = "" if h.get("value") is True else str(h.get("value"))
        f["min"], f["max"] = num(h.get("min")), num(h.get("max"))
    elif kind == "check":
        f["has_max"] = h.get("max") is not None
    return f


def load(text):
    doc = yaml.load(text, Loader=CoreLoader) if text.strip() else {}
    if not isinstance(doc, dict):
        raise ValueError("not a YAML map")
    out, order = {}, []
    for g, hs in (doc.get("groups") or {}).items():
        for i, (hid, raw) in enumerate((hs or {}).items()):
            f = habit(raw)
            f["group"], f["pos"] = str(g), i
            out[str(hid)] = f
            order.append(str(hid))
    ws = str(doc.get("week_start") or "mon")[:3].lower()
    return {"habits": out, "week_start": ws}


def show(v):
    if v is None:
        return "none"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def compare(old, new):
    """Return (split, rescore, info) lists of Markdown bullet texts."""
    split, rescore, info = [], [], []
    O, N = old["habits"], new["habits"]
    if old["week_start"] != new["week_start"] and O:
        rescore.append(f"`week_start` {old['week_start']} → {new['week_start']}: week grouping and `per_week` counts change for all history")
    removed = [h for h in O if h not in N]
    added = [h for h in N if h not in O]
    for r in removed:                                     # same group and position: probably a renamed id
        twin = next((a for a in added if N[a]["group"] == O[r]["group"] and N[a]["pos"] == O[r]["pos"]), None)
        if twin:
            split.append(f"`{r}` → `{twin}` looks like a renamed id: `{r}`'s history stays under `{r}` (hidden) and `{twin}` starts empty. "
                         f"Keep the id and change `name` instead, unless a fresh start is intended.")
    for h in removed:
        info.append(f"removed `{h}` ({O[h]['group']}): history hidden, not deleted")
    for h in added:
        info.append(f"added `{h}` ({N[h]['group']})")
    for h in (x for x in N if x in O):
        o, n = O[h], N[h]
        if o["kind"] != n["kind"]:
            k = f"`{h}`: kind {KIND[o['kind']]} → {KIND[n['kind']]}"
            if frozenset((o["kind"], n["kind"])) in SAFE_KIND:
                rescore.append(k + " (safe pair: old values read by rule)")
            else:
                split.append(k + ". Old values will be misread and the first tap overwrites them; split into a new id")
            continue                                     # threshold diffs between kinds aren't meaningful
        if n["kind"] == "value" and o["unit"] != n["unit"]:
            split.append(f"`{h}`: unit {o['unit'] or 'none'} → {n['unit'] or 'none'}. Old numbers keep the old unit; split into a new id")
        if n["kind"] == "count" and o["count"] != n["count"]:
            rescore.append(f"`{h}`: count {show(o['count'])} → {show(n['count'])}")
        if n["kind"] in ("count", "value"):
            for k in ("min", "max"):
                if o[k] != n[k]:
                    rescore.append(f"`{h}`: {k} {show(o[k])} → {show(n[k])}")
        if n["kind"] == "check" and o["has_max"] != n["has_max"]:
            rescore.append(f"`{h}`: max text {'added' if n['has_max'] else 'removed'} (extra-credit level {'added' if n['has_max'] else 'removed'})")
        if o["days"] != n["days"]:
            rescore.append(f"`{h}`: days {fmt_days(o['days'])} → {fmt_days(n['days'])}")
        for k in ("every", "start", "end", "per_week"):
            if o[k] != n[k]:
                rescore.append(f"`{h}`: {k} {show(o[k])} → {show(n[k])}")
    return split, rescore, info


def report(old_text, new_text, base=None, head=None):
    try:
        old, new = load(old_text), load(new_text)
    except Exception as e:                              # never break CI over the report
        return f"### habits.yaml changes\n\nCould not compare: {e}\n"
    if old == new:
        return ""
    split, rescore, info = compare(old, new)
    rng = f" ({base[:7]} → {head[:7]})" if base and head else f" (since {base[:7]})" if base else ""
    out = [f"### habits.yaml changes{rng}", ""]
    if not (split or rescore or info):
        return "\n".join(out + ["Only free changes (names, notes, order, groups, display). Nothing affects history.", ""])
    for title, items in (("🔴 Split needed", split), ("🟡 Rescores history", rescore), ("🟢 Info", info)):
        if items:
            out += [f"**{title}**", ""] + [f"- {x}" for x in items] + [""]
    out.append(f"See `{DOC}` for what each change does. This report never blocks the deploy.")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("old"); ap.add_argument("new")
    ap.add_argument("--base"); ap.add_argument("--head")
    a = ap.parse_args()
    read = lambda p: pathlib.Path(p).read_text(encoding="utf-8") if pathlib.Path(p).exists() else ""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(report(read(a.old), read(a.new), a.base, a.head))


if __name__ == "__main__":
    main()
