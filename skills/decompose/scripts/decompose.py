#!/usr/bin/env python3
"""Expand task cards into validated steps, or check a unit map and print its plan."""

import argparse
import copy
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitmap  # noqa: E402

try:
    import fcntl
except ImportError:
    fcntl = None

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
RECIPES = Path(__file__).resolve().parents[1] / "recipes.json"
KINDS = {"frame", "code", "test-run", "audit-needed", "ship", "reproduce",
         "search", "fetch", "extract", "synthesize", "read", "audit"}
WRITE_KINDS = {"code", "ship"}
MERGED_KEYS = ("tools_by_kind", "scopes", "plan_defaults")
INPUTS = {
    "frame": ("ask", "purpose", "scope", "paths"),
    "code": ("ask", "scope", "paths", "conventions", "denied"),
    "test-run": ("ask", "paths", "verify", "denied"),
    "audit-needed": ("paths", "range"),
    "ship": ("ask", "denied"),
    "reproduce": ("ask", "scope", "paths", "verify"),
    "search": ("ask", "purpose", "scope"),
    "fetch": ("ask",),
    "extract": ("ask",),
    "synthesize": ("ask", "purpose"),
    "read": ("ask", "scope", "paths"),
    "audit": ("ask", "scope", "paths", "range", "threat_model", "design_decisions"),
}
SCHEMA = {
    "type": "array", "minItems": 1, "items": {
        "type": "object", "required": ["id", "kind", "inputs", "outputs", "deps", "paths", "needs"],
        "properties": {
            "id": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+$"}, "kind": {"enum": sorted(KINDS)},
            **{key: {"type": "array", "items": {"type": "string", "minLength": 1}}
               for key in ("inputs", "outputs", "deps", "paths")},
            "needs": {"type": "object", "required": ["cpu", "ram_gb", "gpu", "disk_gb", "tools"],
                      "properties": {"cpu": {"type": "number", "minimum": 0},
                                     "ram_gb": {"type": "number", "minimum": 0},
                                     "gpu": {"type": "boolean"}, "disk_gb": {"type": "number", "minimum": 0},
                                     "tools": {"type": "array", "items": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+$"}}}}
        }
    }
}


class NeedsModel(ValueError):
    pass


def one_line(value):
    return repr(str(value))[1:-1]


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(one_line(message))


def same_path(left, right):
    if (tuple(unicodedata.normalize("NFC", part).casefold() for part in Path(left).parts) ==
            tuple(unicodedata.normalize("NFC", part).casefold() for part in Path(right).parts)):
        return True
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def path_inside(path, directory):
    return any(same_path(parent, directory) for parent in (path, *path.parents))


def user_recipes_path():
    path = Path(os.environ.get("DECOMPOSE_RECIPES") or
                Path.home() / ".claude/decompose/recipes.json").expanduser().resolve()
    if path_inside(path, PLUGIN_ROOT):
        raise ValueError("user recipes must be outside the plugin directory")
    return path


@contextmanager
def recipe_lock(path):
    lock = path.with_name(path.name + ".lock")
    if fcntl is not None:
        with lock.open("a") as out:
            fcntl.flock(out.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(out.fileno(), fcntl.LOCK_UN)
        return
    deadline = time.monotonic() + 10
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ValueError("timed out waiting for recipe lock: " + str(lock))
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink()


def read_recipes(path):
    recipes = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(recipes, dict):
        raise ValueError("recipes must be an object: " + str(path))
    for key in MERGED_KEYS:
        if key in recipes and not isinstance(recipes[key], dict):
            raise ValueError(key + " must be an object")
    return recipes


def load_recipes():
    recipes = read_recipes(RECIPES)
    path = user_recipes_path()
    if path.exists():
        for name, recipe in read_recipes(path).items():
            if name in MERGED_KEYS:
                recipes.setdefault(name, {}).update(recipe)
            else:
                recipes[name] = recipe
    return recipes


def topological_waves(steps):
    """Group ready steps in input order. Call after schema and dependency checks."""
    remaining = list(steps)
    done, waves = set(), []
    while remaining:
        wave = [step for step in remaining if set(step["deps"]) <= done]
        if not wave:
            raise ValueError("dependency cycle")
        done.update(step["id"] for step in wave)
        waves.append(wave)
        remaining = [step for step in remaining if step["id"] not in done]
    return waves


def tools_list(value):
    if isinstance(value, str):
        if value.strip().startswith("["):
            try:
                value = json.loads(value)
            except (ValueError, RecursionError) as exc:
                raise ValueError("invalid tools JSON: " + str(exc)) from exc
        else:
            value = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, list) or any(
            not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", tag) for tag in value):
        raise ValueError("tools must be an array or comma-separated capability names")
    return sorted(set(value))


def parse_task(text):
    """Read CARD.md front matter and its named body fields without YAML dependencies."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("card must begin with --- front matter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise ValueError("card front matter must end with ---") from exc
    card = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([a-z_]+):\s*(.*)", line)
        if not match:
            raise ValueError("invalid card field")
        key, value = match.groups()
        if key in card and key != "verify":
            raise ValueError("duplicate card field: " + key)
        if value.startswith('"'):
            value, tail = json.JSONDecoder().raw_decode(value)
            if match[2][tail:].strip() and not match[2][tail:].strip().startswith("#"):
                raise ValueError("unexpected text after quoted value")
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if key == "tools":
            card[key] = tools_list(value)
        elif key == "verify":
            card.setdefault(key, []).append(value)
        else:
            card[key] = value
    body = "\n".join(lines[end + 1:])
    card["body"] = body
    labels = list(re.finditer(r"^\*\*([^\n]+?)\.\*\*\s*", body, re.M))
    names = {"Purpose": "purpose", "Scope of build": "scope", "Required RED cases": "red_cases",
             "Threat model": "threat_model", "Design decisions": "design_decisions",
             "Denied actions": "denied", "Conventions": "conventions"}
    for index, match in enumerate(labels):
        if match[1] in names:
            stop = labels[index + 1].start() if index + 1 < len(labels) else len(body)
            card[names[match[1]]] = body[match.end():stop].strip()
    return card


def decompose(card):
    recipes = load_recipes()
    name = card.get("kind") or card.get("mode")
    recipe = recipes.get(name)
    if recipe is None:
        raise NeedsModel(str(name or "unspecified"))
    if not isinstance(recipe, dict):
        raise ValueError("recipe must be an object: " + str(name))
    if "steps" in recipe:
        steps = copy.deepcopy(recipe["steps"])
        errors = validate(steps)
        if errors:
            raise ValueError("invalid recipe: " + "; ".join(errors))
    else:
        kinds = recipe.get("kinds")
        if not isinstance(kinds, list) or not kinds:
            raise ValueError("recipe kinds must be a nonempty array")
        for kind in kinds:
            if not isinstance(kind, str) or kind not in KINDS:
                raise ValueError("unknown kind: " + str(kind))
        paths = card.get("paths", [])
        if isinstance(paths, str):
            paths = [p.strip() for p in paths.split(",") if p.strip()]
        steps = []
        if not isinstance(paths, list):
            raise ValueError("card paths must be an array or comma-separated paths")
        for kind in kinds:
            if kind == "ship" and any(str(card.get(key, "")).strip().lower() == "no" for key in ("push", "ship")):
                continue
            previous = steps[-1]["id"] if steps else None
            inputs = [field for field in INPUTS[kind] if field in card]
            if previous:
                inputs.append("step:" + previous)
            steps.append({"id": kind, "kind": kind, "inputs": inputs,
                          "outputs": [kind + "-result"], "deps": [previous] if previous else [],
                          "paths": list(paths) if kind == "code" else [],
                          "needs": {"cpu": 1, "ram_gb": 1, "gpu": False, "disk_gb": 1}})
    if any(str(card.get(key, "")).strip().lower() == "no" for key in ("push", "ship")):
        removed = {step["id"]: step for step in steps if step.get("kind") == "ship"}
        def predecessors(ident, seen=None):
            if ident not in removed:
                return [ident]
            seen = (seen or set()) | {ident}
            return [item for dep in removed[ident].get("deps", []) if dep not in seen
                    for item in predecessors(dep, seen)]
        steps = [step for step in steps if step.get("kind") != "ship"]
        for step in steps:
            step["deps"] = list(dict.fromkeys(item for dep in step["deps"] for item in predecessors(dep)))
            step["inputs"] = list(dict.fromkeys(
                item for name in step["inputs"] for item in
                (["step:" + dep for dep in predecessors(name[5:])] if name.startswith("step:") and name[5:] in removed else [name])))
    card_tools = tools_list(card.get("tools", []))
    defaults = recipes.get("tools_by_kind", {})
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("needs"), dict):
            continue
        needs = step["needs"]
        tools = needs.get("tools", defaults.get(step.get("kind"), []))
        needs["tools"] = sorted(set(tools_list(tools) + card_tools))
    errors = validate(steps)
    if errors:
        raise ValueError("invalid decomposition: " + "; ".join(errors))
    return steps


def validate(steps):
    errors = []
    if not isinstance(steps, list) or not steps:
        return ["steps must be a nonempty array"]
    ids = set()
    for step in steps:
        if not isinstance(step, dict):
            errors.append("each step must be an object")
            continue
        ident, kind = step.get("id"), step.get("kind")
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", ident):
            errors.append("invalid step id")
        elif ident in ids:
            errors.append("duplicate step id: " + ident)
        else:
            ids.add(ident)
        if not isinstance(kind, str) or kind not in KINDS:
            errors.append("unknown kind: " + str(kind))
        for field in ("inputs", "outputs", "deps", "paths"):
            value = step.get(field)
            if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
                errors.append(str(ident) + ": invalid " + field)
        needs = step.get("needs")
        if not isinstance(needs, dict):
            errors.append(str(ident) + ": invalid needs")
        else:
            tools = needs.get("tools")
            if not isinstance(tools, list) or any(
                    not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", tag) for tag in tools):
                errors.append(str(ident) + ": invalid needs.tools")
            for key in ("cpu", "ram_gb", "disk_gb"):
                value = needs.get(key)
                try:
                    valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                             and value >= 0 and math.isfinite(value))
                except OverflowError:
                    valid = False
                if not valid:
                    errors.append(str(ident) + ": invalid needs." + key)
            if not isinstance(needs.get("gpu"), bool):
                errors.append(str(ident) + ": invalid needs.gpu")
    if errors:
        return errors
    graph = {s["id"]: s["deps"] for s in steps}
    for ident, deps in graph.items():
        for dep in deps:
            if dep not in graph:
                errors.append(ident + ": unknown dependency " + dep)
    if not errors:
        try:
            topological_waves(steps)
        except ValueError as exc:
            errors.append(str(exc))
    writes = []
    for step in steps:
        if step["kind"] not in WRITE_KINDS:
            continue
        for path in step["paths"]:
            if not Path(path).is_absolute():
                errors.append(step["id"] + ": write path must be absolute")
                continue
            resolved = Path(path).resolve()
            for owner, other in writes:
                if owner != step["id"] and (path_inside(resolved, other) or path_inside(other, resolved)):
                    errors.append("overlapping write paths: " + owner + " and " + step["id"])
            writes.append((step["id"], resolved))
    return errors


def save_recipe(name, steps):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("invalid recipe name")
    errors = validate(steps)
    if errors:
        raise ValueError("; ".join(errors))
    path = user_recipes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with recipe_lock(path):
        if name in load_recipes():
            raise ValueError("recipe already exists: " + name)
        recipes = read_recipes(path) if path.exists() else {}
        recipes[name] = {"status": "candidate", "steps": steps}
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".recipes-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(recipes, out, indent=2, allow_nan=False)
                out.write("\n")
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("card", nargs="?", help="CARD.md task file")
    parser.add_argument("--task", help="CARD.md task file")
    parser.add_argument("--validate", metavar="STEPS_JSON")
    parser.add_argument("--save-recipe", metavar="NAME")
    parser.add_argument("--waves", action="store_true", help="print JSON arrays of steps in dependency waves")
    parser.add_argument("--plan", metavar="PLAN_JSON", help="check a unit map and print its plan table")
    parser.add_argument("--apply-patch", metavar="PATCH_JSON", help="apply an advisor patch to --plan first")
    parser.add_argument("--json", action="store_true", help="with --plan, print the computed plan as JSON")
    args = parser.parse_args(argv)
    if args.save_recipe and not args.validate:
        parser.error("--save-recipe requires --validate")
    if args.plan and (args.validate or args.card or args.task or args.waves):
        parser.error("--plan cannot be combined with a card, --validate or --waves")
    if (args.apply_patch or args.json) and not args.plan:
        parser.error("--apply-patch and --json require --plan")
    try:
        if args.plan:
            plan = unitmap.normalize(json.loads(Path(args.plan).read_text(encoding="utf-8")))
            errors = unitmap.validate(plan, same_path, path_inside)
            if errors:
                raise ValueError("; ".join(errors))
            if args.apply_patch:
                advice = json.loads(Path(args.apply_patch).read_text(encoding="utf-8"))
                plan = unitmap.apply_patch(plan, advice)
                errors = unitmap.validate(plan, same_path, path_inside)
                if errors:
                    raise ValueError("patch rejected, map unchanged: " + "; ".join(errors))
            limits = unitmap.defaults(load_recipes().get("plan_defaults"))
            result = unitmap.compute(plan, limits)
            if args.json:
                print(json.dumps({"ask": plan["ask"], "clauses": plan["clauses"],
                                  "patched": bool(args.apply_patch), **result}, indent=2))
            else:
                print(unitmap.table(plan, result, patched=bool(args.apply_patch)))
            return 0
        if args.validate:
            steps = json.loads(Path(args.validate).read_text(encoding="utf-8"))
            errors = validate(steps)
            if errors:
                raise ValueError("; ".join(errors))
            if args.save_recipe:
                save_recipe(args.save_recipe, steps)
            if not args.waves:
                print("DECOMPOSE valid")
        else:
            path = args.task or args.card
            if not path:
                parser.error("a task card is required")
            steps = decompose(parse_task(Path(path).read_text(encoding="utf-8")))
        if args.waves:
            print(json.dumps(topological_waves(steps), indent=2))
        elif not args.validate:
            print(json.dumps(steps, indent=2))
    except NeedsModel as exc:
        print("DECOMPOSE needs-model " + one_line(exc), file=sys.stderr)
        print(json.dumps(SCHEMA, indent=2))
        return 3
    except (ValueError, OSError, json.JSONDecodeError, RecursionError) as exc:
        print("DECOMPOSE error: " + one_line(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
