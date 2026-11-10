"""Register the aunx-decompose skill and command with Hermes Agent."""

import os
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent

# The bundled skill references ${CLAUDE_PLUGIN_ROOT}; make it resolve under Hermes
# without clobbering the value Claude Code sets itself.
os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(_PLUGIN_DIR))
os.environ.setdefault(
    "DECOMPOSE_RECIPES", str(Path.home() / ".hermes" / "decompose" / "recipes.json")
)


def _handle_decompose(raw_args: str) -> str:
    task = (raw_args or "").strip()
    if not task:
        return (
            "Usage: /decompose <task>\n\n"
            "Load the skill `aunx-decompose:decompose` and follow it to plan, "
            "validate, and print parallel waves. The plugin never executes the plan."
        )
    return (
        f"Decompose task: {task}\n\n"
        "Load the skill `aunx-decompose:decompose` and follow its steps to turn "
        "this into validated steps and parallel waves. Do not execute the plan."
    )


def register(ctx):
    ctx.register_skill(
        "decompose", _PLUGIN_DIR / "skills" / "decompose" / "SKILL.md",
        description="Split a task into checkable units and parallel waves.",
    )
    ctx.register_command(
        "decompose", _handle_decompose,
        description="Split a task into checkable units and parallel waves.",
        args_hint="<task>",
    )
