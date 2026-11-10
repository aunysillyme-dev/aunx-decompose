"""Check a unit map, compute its waves, and print the plan.

A unit map is the fine-grained form of a plan. Each unit has its own input,
output and verifier, a type and a speed class, and the clause of the ask it
serves. This module never picks models or machines. It leaves those columns
for the agent, which fills them by the method in references/picking.md.
"""

from collections import Counter
import copy
import math
from pathlib import Path
import re

TYPES = ("coding", "reasoning", "research", "writing", "creative-image", "creative-video",
         "creative-audio", "creative-music", "design", "vision", "review", "data", "agentic",
         "cyber")
SPEEDS = ("fast", "standard", "frontier")
IMPORTANCE = ("low", "medium", "high")
SHAPES = ("single", "subagents", "bulk-prompt", "agent-fanout", "split-worktrees")
# Read, draft and extract work: the kinds an agent fan-out handles well.
FANOUT_TYPES = {"research", "writing", "data", "vision", "review"}
# Types that act on a system, so they are never a tool-free prompt.
ACTING_TYPES = {"coding", "agentic", "cyber"}
DEFAULTS = {
    "advisor_max_steps": 5, "advisor_min_units": 12, "advisor_serial_min_steps": 4,
    "advisor_serial_ratio": 0.75, "advisor_min_readers": 3, "high_importance_readers": 3,
    "agent_fanout_min": 10, "bulk_prompt_min": 2, "subagents_min": 4,
}
NAME = re.compile(r"[A-Za-z0-9_.-]+")
REQUIRED = ("id", "type", "speed", "clause_ids", "inputs", "outputs", "deps", "paths", "verify")
OPTIONAL = ("parent_id", "importance", "is_invalidator", "item_count", "dispatch_hint", "needs",
            "irreversible", "context_tokens", "model", "machine", "runner_up", "effort", "note")
COMPUTED_PLAN_KEYS = {"advisor", "waves", "critical_path", "coverage", "steps", "patched",
                      "warnings", "questions"}
COMPUTED_UNIT_KEYS = {"wave", "parallel_group", "downstream_readers", "shape", "shape_reason"}
NEEDS_NUMBERS = ("cpu", "ram_gb", "disk_gb", "minutes")
NEEDS_FLAGS = ("gpu", "scale_up", "local_only")
PATCH_OPS = ("split", "cut_edges", "retier", "dispatch", "needs")
ADVICE_KEYS = {"patch", "granularity", "reframe", "mistakes", "reasons"}


def _number(value):
    try:
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and value >= 0 and math.isfinite(value))
    except OverflowError:
        return False


def _strings(value):
    return isinstance(value, list) and all(isinstance(v, str) and v for v in value)


def defaults(overrides=None):
    merged = dict(DEFAULTS)
    for key, value in (overrides or {}).items():
        if key not in DEFAULTS or not _number(value):
            raise ValueError("invalid plan default: " + str(key))
        merged[key] = value
    return merged


def normalize(data):
    """Accept {"ask", "clauses", "units"} or a bare array of units."""
    if isinstance(data, list):
        data = {"units": data}
    if not isinstance(data, dict):
        raise ValueError("plan must be an object or an array of units")
    extra = set(data) - {"ask", "clauses", "units"} - COMPUTED_PLAN_KEYS
    if extra:
        raise ValueError("unknown plan field: " + sorted(extra)[0])
    clauses = data.get("clauses")
    if isinstance(clauses, list):
        table = {}
        for clause in clauses:
            if isinstance(clause, str):
                ident, text = clause, ""
            elif isinstance(clause, dict) and set(clause) <= {"id", "text"}:
                ident, text = clause.get("id"), clause.get("text", "")
            else:
                raise ValueError("each clause must be an id or {id, text}")
            if not isinstance(ident, str) or not NAME.fullmatch(ident) or not isinstance(text, str):
                raise ValueError("invalid clause")
            if ident in table:
                raise ValueError("duplicate clause: " + ident)
            table[ident] = text
        clauses = table
    elif isinstance(clauses, dict):
        if not all(isinstance(k, str) and NAME.fullmatch(k) and isinstance(v, str)
                   for k, v in clauses.items()):
            raise ValueError("invalid clause")
    else:
        raise ValueError("plan needs clauses: the numbered parts of the ask")
    if not clauses:
        raise ValueError("plan needs at least one clause")
    units = data.get("units")
    if isinstance(units, list):
        units = [{k: v for k, v in unit.items() if k not in COMPUTED_UNIT_KEYS}
                 if isinstance(unit, dict) else unit for unit in units]
    return {"ask": data.get("ask", ""), "clauses": clauses, "units": units}


def _unit_errors(unit, errors):
    ident = unit.get("id") if isinstance(unit.get("id"), str) else "?"
    for key in REQUIRED:
        if key not in unit:
            errors.append(ident + ": missing " + key)
    for key in set(unit) - set(REQUIRED) - set(OPTIONAL):
        errors.append(ident + ": unknown field " + key)
    if unit.get("type") not in TYPES:
        errors.append(ident + ": unknown type " + str(unit.get("type")))
    if unit.get("speed") not in SPEEDS:
        errors.append(ident + ": unknown speed " + str(unit.get("speed")))
    for key in ("clause_ids", "inputs", "outputs"):
        if key in unit and (not _strings(unit[key]) or not unit[key]):
            errors.append(ident + ": " + key + " must be a nonempty array of strings")
    for key in ("deps", "paths"):
        if key in unit and not _strings(unit[key]):
            errors.append(ident + ": invalid " + key)
    if "verify" in unit and (not isinstance(unit["verify"], str) or not unit["verify"].strip()):
        errors.append(ident + ": verify must say how the output is checked")
    if unit.get("parent_id") is not None and (
            not isinstance(unit["parent_id"], str) or not NAME.fullmatch(unit["parent_id"])):
        errors.append(ident + ": invalid parent_id")
    if unit.get("importance", "medium") not in IMPORTANCE:
        errors.append(ident + ": invalid importance")
    for key in ("is_invalidator", "irreversible"):
        if not isinstance(unit.get(key, False), bool):
            errors.append(ident + ": invalid " + key)
    count = unit.get("item_count", 1)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        errors.append(ident + ": item_count must be a positive integer")
    if unit.get("dispatch_hint") is not None and unit["dispatch_hint"] not in SHAPES:
        errors.append(ident + ": unknown dispatch_hint " + str(unit["dispatch_hint"]))
    context = unit.get("context_tokens")
    if context is not None and (isinstance(context, bool) or not isinstance(context, int) or context < 1):
        errors.append(ident + ": invalid context_tokens")
    for key in ("model", "machine", "runner_up", "effort", "note"):
        if key in unit and not isinstance(unit[key], str):
            errors.append(ident + ": invalid " + key)
    needs = unit.get("needs", {})
    if not isinstance(needs, dict):
        errors.append(ident + ": invalid needs")
        return
    for key in set(needs) - set(NEEDS_NUMBERS) - set(NEEDS_FLAGS) - {"capabilities"}:
        errors.append(ident + ": unknown needs." + key)
    for key in NEEDS_NUMBERS:
        if key in needs and not _number(needs[key]):
            errors.append(ident + ": invalid needs." + key)
    for key in NEEDS_FLAGS:
        if not isinstance(needs.get(key, False), bool):
            errors.append(ident + ": invalid needs." + key)
    caps = needs.get("capabilities", [])
    if not isinstance(caps, list) or any(not isinstance(c, str) or not NAME.fullmatch(c) for c in caps):
        errors.append(ident + ": invalid needs.capabilities")


def _ancestors(units):
    deps = {u["id"]: u["deps"] for u in units}
    seen = {}

    def walk(ident):
        if ident not in seen:
            seen[ident] = set()
            for dep in deps[ident]:
                seen[ident] |= {dep} | walk(dep)
        return seen[ident]

    for ident in deps:
        walk(ident)
    return seen


def layers(units):
    """Kahn layering: wave 0 holds units with no deps; each later wave is 1 + max(dep waves)."""
    remaining, done, waves = list(units), set(), []
    while remaining:
        wave = [u for u in remaining if set(u["deps"]) <= done]
        if not wave:
            raise ValueError("dependency cycle")
        done.update(u["id"] for u in wave)
        waves.append(wave)
        remaining = [u for u in remaining if u["id"] not in done]
    return waves


def validate(plan, same_path=None, path_inside=None):
    """Return a list of errors. An empty list means the map is valid."""
    errors = []
    units = plan["units"]
    if not isinstance(units, list) or not units:
        return ["units must be a nonempty array"]
    ids = set()
    for unit in units:
        if not isinstance(unit, dict):
            return ["each unit must be an object"]
        _unit_errors(unit, errors)
        ident = unit.get("id")
        if not isinstance(ident, str) or not NAME.fullmatch(ident):
            errors.append("invalid unit id")
        elif ident in ids:
            errors.append("duplicate unit id: " + ident)
        else:
            ids.add(ident)
    if errors:
        return errors
    by_id = {u["id"]: u for u in units}
    for unit in units:
        parent = unit.get("parent_id")
        if parent is None:
            continue
        if not unit["id"].startswith(parent + "."):
            errors.append(unit["id"] + ": a substep id starts with its parent id and a dot")
        if parent in by_id:
            errors.append(unit["id"] + ": parent " + parent + " is structural; remove its row once split")
        if parent.count(".") or any(other.get("id") == parent and other.get("parent_id")
                                    for other in units):
            errors.append(unit["id"] + ": substeps go one level deep")
    # Clause coverage, both ways.
    clauses = plan["clauses"]
    used = set()
    for unit in units:
        for clause in unit["clause_ids"]:
            if clause not in clauses:
                errors.append(unit["id"] + ": unknown clause " + clause)
            used.add(clause)
    for clause in clauses:
        if clause not in used:
            errors.append("clause " + clause + " has no unit")
    # Outputs are namespaced: one producer per output name.
    producer = {}
    for unit in units:
        for output in unit["outputs"]:
            if output in producer:
                errors.append("output " + output + " is produced by " + producer[output] +
                              " and " + unit["id"] + "; name outputs per unit")
            producer[output] = unit["id"]
    for unit in units:
        for dep in unit["deps"]:
            if dep == unit["id"]:
                errors.append(unit["id"] + ": depends on itself")
            elif dep not in by_id:
                errors.append(unit["id"] + ": unknown dependency " + dep)
            elif not set(unit["inputs"]) & set(by_id[dep]["outputs"]):
                errors.append("false edge " + dep + " -> " + unit["id"] + ": " + unit["id"] +
                              " reads none of " + dep + "'s outputs")
        for item in unit["inputs"]:
            source = producer.get(item)
            if source and source != unit["id"] and source not in unit["deps"]:
                errors.append("missing edge " + source + " -> " + unit["id"] + ": " +
                              unit["id"] + " reads " + item)
            if source == unit["id"]:
                errors.append(unit["id"] + ": reads its own output " + item)
    if errors:
        return errors
    try:
        layers(units)
    except ValueError as exc:
        return [str(exc)]
    # Writes: absolute, and disjoint between units that could run at the same time.
    ancestors = _ancestors(units)
    writes = []
    for unit in units:
        for path in unit["paths"]:
            if not Path(path).is_absolute():
                errors.append(unit["id"] + ": write path must be absolute")
                continue
            resolved = Path(path).resolve()
            for owner, other in writes:
                ordered = owner in ancestors[unit["id"]] or unit["id"] in ancestors[owner]
                if owner != unit["id"] and not ordered and (
                        path_inside(resolved, other) or path_inside(other, resolved)):
                    errors.append("overlapping write paths: " + owner + " and " + unit["id"] +
                                  " can run at the same time")
            writes.append((unit["id"], resolved))
    return errors


def _shape(group, limits):
    """Pick a dispatch shape for a group of units. First match wins."""
    n = sum(u.get("item_count", 1) for u in group)
    caps = lambda u: u.get("needs", {}).get("capabilities", [])
    if n == 1:
        return "single", "one unit"
    if n >= limits["agent_fanout_min"] and all(not u["paths"] and u["type"] in FANOUT_TYPES
                                               for u in group):
        return "agent-fanout", "N=%d >= agent_fanout_min %g" % (n, limits["agent_fanout_min"])
    if n >= limits["bulk_prompt_min"] and all(not u["paths"] and not caps(u) and
                                              u["type"] not in ACTING_TYPES for u in group):
        return "bulk-prompt", "N=%d tool-free >= bulk_prompt_min %g" % (n, limits["bulk_prompt_min"])
    if len(group) >= 2 and all(u["paths"] for u in group):
        return "split-worktrees", "%d writers on disjoint paths" % len(group)
    if n >= limits["subagents_min"]:
        return "subagents", "N=%d >= subagents_min %g" % (n, limits["subagents_min"])
    return "single", "N=%d below every threshold: one call per unit" % n


def _critical_path(units, waves):
    minutes = {u["id"]: u.get("needs", {}).get("minutes") for u in units}
    known = all(value is not None for value in minutes.values())
    weight = {k: (v if known else 1) for k, v in minutes.items()}
    best, prev = {}, {}
    for wave in waves:
        for unit in wave:
            top = max(unit["deps"], key=lambda d: (best[d], d), default=None)
            best[unit["id"]] = weight[unit["id"]] + (best[top] if top else 0)
            prev[unit["id"]] = top
    end = max(best, key=lambda k: (best[k], k))
    path = [end]
    while prev[path[-1]]:
        path.append(prev[path[-1]])
    path.reverse()
    result = {"units": path, "length": best[end], "measure": "minutes" if known else "units"}
    if known:
        result["serial_minutes"] = sum(weight.values())
    else:
        result["minutes_unknown"] = sorted(k for k, v in minutes.items() if v is None)
    return result


def compute(plan, limits):
    """Add waves, groups, readers, importance, shapes, the advisor gate and coverage."""
    units = copy.deepcopy(plan["units"])
    readers = Counter(dep for u in units for dep in set(u["deps"]))
    top = lambda u: u.get("parent_id") or u["id"]
    waves = layers(units)
    for index, wave in enumerate(waves):
        wave.sort(key=lambda u: (not u.get("is_invalidator", False), -readers[u["id"]], u["id"]))
        group = "W%d" % index if len(wave) >= 2 else None
        # A shape is chosen per step inside the wave: one step's sibling substeps share it.
        siblings = {}
        for unit in wave:
            siblings.setdefault(unit.get("parent_id") or unit["id"], []).append(unit)
        shapes = {key: _shape(members, limits) for key, members in siblings.items()}
        for unit in wave:
            wave_shape = shapes[unit.get("parent_id") or unit["id"]]
            unit["wave"] = index
            unit["parallel_group"] = group
            unit["downstream_readers"] = readers[unit["id"]]
            stated = unit.get("importance", "medium")
            floor = ("high" if readers[unit["id"]] >= limits["high_importance_readers"] else
                     "medium" if readers[unit["id"]] >= 1 else "low")
            unit["importance"] = max(stated, floor, key=IMPORTANCE.index)
            if unit.get("dispatch_hint"):
                unit["shape"], unit["shape_reason"] = unit["dispatch_hint"], "dispatch_hint"
            elif unit.get("item_count", 1) > 1:
                unit["shape"], unit["shape_reason"] = _shape([unit], limits)
            else:
                unit["shape"], unit["shape_reason"] = wave_shape
        writers = [u for u in wave if u["paths"] and u["shape"] == "single"
                   and not u.get("dispatch_hint")]
        if len({top(u) for u in writers}) >= 2:
            for unit in writers:
                unit["shape"] = "split-worktrees"
                unit["shape_reason"] = "%d writers in this wave on disjoint paths" % len(writers)
    ordered = [u for wave in waves for u in wave]
    critical_path = _critical_path(ordered, waves)
    path_question = ("Critical path %s (%g %s): which edge on it is not a real data edge "
                     "or could start from a partial output?" %
                     (" -> ".join(critical_path["units"]), critical_path["length"],
                      critical_path["measure"]))
    # Advisor gate.
    by_id = {u["id"]: u for u in ordered}
    steps = sorted({top(u) for u in ordered})
    reasons, questions = [], []
    if len(steps) > limits["advisor_max_steps"]:
        reasons.append("steps=%d > %g" % (len(steps), limits["advisor_max_steps"]))
        counts = Counter(top(u) for u in ordered)
        smallest = sorted(steps, key=lambda s: (counts[s], s))[:2]
        questions.append(reasons[-1] + ": could the smallest steps, " +
                         ", ".join("%s (%d units)" % (s, counts[s]) for s in smallest) + " merge?")
    if len(ordered) >= limits["advisor_min_units"]:
        reasons.append("units=%d >= %g" % (len(ordered), limits["advisor_min_units"]))
        groups = {}
        for unit in ordered:
            groups.setdefault((unit["type"], unit["speed"]), []).append(unit["id"])
        kind, speed = min(groups, key=lambda key: (-len(groups[key]), key))
        members = sorted(groups[(kind, speed)])
        questions.append(reasons[-1] + ": largest same type and speed group is " +
                         "%s x %s (%d units: %s); does item_count fit this work?" %
                         (kind, speed, len(members), ", ".join(members)))
    if len(steps) >= limits["advisor_serial_min_steps"]:
        step_units = [{"id": s, "deps": sorted({top(by_id[d]) for u in ordered if top(u) == s
                                                for d in u["deps"]} - {s})} for s in steps]
        try:
            depth = len(layers(step_units))
        except ValueError:
            reasons.append("substeps interleave across steps")
            questions.append("Substeps interleave across %d steps (%s). " %
                             (len(steps), ", ".join(steps)) + path_question)
        else:
            if depth / len(steps) > limits["advisor_serial_ratio"]:
                reasons.append("nearly serial: %d step waves for %d steps" % (depth, len(steps)))
                questions.append(reasons[-1] + ". " + path_question)
    for unit in ordered:
        if unit["downstream_readers"] >= limits["advisor_min_readers"]:
            reasons.append("%s read by %d units" % (unit["id"], unit["downstream_readers"]))
            tail = "?" if unit.get("is_invalidator") else ", and should it be an invalidator?"
            questions.append(reasons[-1] + ": is %s verified before its readers start%s" % (unit["id"], tail))
    inputs = {item for u in ordered for item in u["inputs"]}
    warnings = ["%s: orphan output %s has no reader" % (u["id"], output)
                for u in ordered if readers[u["id"]]
                for output in u["outputs"] if output not in inputs]
    if reasons and not any(u.get("is_invalidator") for u in ordered):
        warnings.append("No invalidator: advisor review is REQUIRED for " + "; ".join(reasons))
    coverage = {c: [u["id"] for u in ordered if c in u["clause_ids"]] for c in plan["clauses"]}
    return {
        "units": ordered,
        "waves": [[u["id"] for u in wave] for wave in waves],
        "critical_path": critical_path,
        "advisor": {"required": bool(reasons), "reasons": reasons},
        "warnings": warnings,
        "questions": questions,
        "coverage": coverage,
        "steps": steps,
    }


def table(plan, result, patched=False):
    cell = lambda value: str(value if value not in (None, "") else "-").replace("|", "\\|")
    lines = ["| unit | parent | clause | type x speed | wave | group | shape | model | machine | runner-up |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for u in result["units"]:
        lines.append("| " + " | ".join(cell(v) for v in (
            u["id"] + (" (invalidator)" if u.get("is_invalidator") else ""), u.get("parent_id"),
            ",".join(u["clause_ids"]), u["type"] + " x " + u["speed"], u["wave"],
            u["parallel_group"], u["shape"], u.get("model"), u.get("machine"),
            u.get("runner_up"))) + " |")
    out = ["PLAN valid", ""]
    gate = result["advisor"]
    if patched:
        out.append("Advisor review: patch applied; gate reasons on the patched map: " +
                   ("; ".join(gate["reasons"]) or "none"))
    else:
        out.append("Advisor review: " + ("REQUIRED before picks (" + "; ".join(gate["reasons"]) + ")"
                                         if gate["required"] else "not required"))
    out += ["", *lines, "", "Waves:"]
    for index, wave in enumerate(result["waves"]):
        out.append("  W%d: %s" % (index, ", ".join(wave)))
    path = result["critical_path"]
    out.append("Critical path (%s): %s, length %g" % (path["measure"], " -> ".join(path["units"]),
                                                       path["length"]))
    if "serial_minutes" in path:
        out.append("Serial estimate: %g minutes. Both figures come from the units' own needs.minutes."
                   % path["serial_minutes"])
    else:
        out.append("needs.minutes missing for: " + ", ".join(path["minutes_unknown"]))
    out.append("Clause coverage:")
    for clause, ids in result["coverage"].items():
        text = plan["clauses"][clause]
        out.append("  %s%s: %s" % (clause, " (" + text + ")" if text else "", ", ".join(ids)))
    for title, key in (("Warnings:", "warnings"), ("Advisor questions:", "questions")):
        if result[key]:
            out += [title, *("  " + item for item in result[key])]
    return "\n".join(out)


def apply_patch(plan, advice):
    """Apply an advisor patch all-or-nothing. Returns a new plan; never edits the input."""
    if not isinstance(advice, dict):
        raise ValueError("patch must be an object")
    if "patch" in advice:
        extra = set(advice) - ADVICE_KEYS
        if extra:
            raise ValueError("unknown advice field: " + sorted(extra)[0])
        patch = advice["patch"]
    else:
        patch = advice
    if not isinstance(patch, dict) or set(patch) - set(PATCH_OPS):
        raise ValueError("patch ops are " + ", ".join(PATCH_OPS) +
                         "; a missing edge cannot be patched, so rebuild the map")
    for op in PATCH_OPS:
        if not isinstance(patch.get(op, []), list) or not all(
                isinstance(item, dict) for item in patch.get(op, [])):
            raise ValueError(op + ": expected a list of objects")
    new = copy.deepcopy(plan)
    units = new["units"]
    index = lambda ident: next((i for i, u in enumerate(units) if u.get("id") == ident), None)

    def find(ident, op):
        i = index(ident)
        if i is None:
            raise ValueError(op + ": unknown unit " + str(ident))
        return units[i]

    for op in patch.get("split", []):
        parent = find(op.get("id"), "split")
        children = op.get("into")
        if set(op) - {"id", "into"} or not isinstance(children, list) or len(children) < 2:
            raise ValueError("split: give id and at least two children in into")
        root = parent.get("parent_id") or parent["id"]
        made = []
        for child in children:
            if not isinstance(child, dict) or not isinstance(child.get("id"), str):
                raise ValueError("split: each child needs an id")
            if not re.fullmatch(re.escape(root) + r"\.\d+", child["id"]) or index(child["id"]) is not None:
                raise ValueError("split: child ids are new " + root + ".<n> ids")
            if "outputs" not in child:
                raise ValueError("split: " + child["id"] + " needs its own outputs")
            row = {k: copy.deepcopy(v) for k, v in parent.items() if k not in ("id", "outputs", "paths")}
            row.update(copy.deepcopy(child))
            row["parent_id"] = root
            row.setdefault("paths", [])
            made.append(row)
        if sorted(p for c in made for p in c["paths"]) != sorted(parent["paths"]):
            raise ValueError("split: child paths must partition the parent's paths exactly")
        produced = {o for c in made for o in c["outputs"]}
        if not set(parent["outputs"]) <= produced:
            raise ValueError("split: children must produce every output of " + parent["id"])
        for unit in units:
            if parent["id"] in unit.get("deps", []):
                feeders = [c["id"] for c in made if c["type"] == "review" or
                           set(c["outputs"]) & set(unit["inputs"])]
                unit["deps"] = [d for d in unit["deps"] if d != parent["id"]] + feeders
                for child in made:
                    if child["type"] == "review":
                        unit["inputs"].extend(o for o in child["outputs"] if o not in unit["inputs"])
        at = index(parent["id"])
        units[at:at + 1] = made
    for op in patch.get("cut_edges", []):
        source, target = find(op.get("from"), "cut_edges"), find(op.get("to"), "cut_edges")
        if source["id"] not in target["deps"]:
            raise ValueError("cut_edges: no edge " + source["id"] + " -> " + target["id"])
        target["deps"].remove(source["id"])
        target["inputs"] = [i for i in target["inputs"] if i not in source["outputs"]]
    for op in patch.get("retier", []):
        unit = find(op.get("id"), "retier")
        if not set(op) & {"type", "speed"}:
            raise ValueError("retier: give type or speed")
        if op.get("speed") == "frontier" and not str(op.get("reason", "")).strip():
            raise ValueError("retier: frontier needs a reason")
        for key in ("type", "speed"):
            if key in op:
                unit[key] = op[key]
    for op in patch.get("dispatch", []):
        find(op.get("id"), "dispatch")["dispatch_hint"] = op.get("dispatch_hint")
    for op in patch.get("needs", []):
        unit = find(op.get("id"), "needs")
        if not isinstance(op.get("needs"), dict):
            raise ValueError("needs: give a needs object")
        unit.setdefault("needs", {}).update(op["needs"])
    return new
