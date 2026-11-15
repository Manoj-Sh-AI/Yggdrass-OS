"""Small approved application skill registry; no arbitrary paths or script execution."""

from pathlib import Path

SKILLS = {
    "tasks": (
        "task-management",
        "Create and revise work while preserving goals and execution history.",
    ),
    "calendar": (
        "calendar-precision",
        "Handle exact intervals, date ranges and uncertainty without inventing time.",
    ),
    "yggdras": (
        "request-routing",
        "Choose an answer, one specialist, or a bounded multi-step workflow.",
    ),
}


def index(agent):
    name, description = SKILLS[agent]
    return f"Available skill: {name} — {description}. Load it on demand with load_skill."


def tool(agent):
    name = SKILLS[agent][0]
    return {
        "name": "load_skill",
        "description": "Load the approved procedural skill for this role. This grants no additional tools or permissions.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "enum": [name]}},
            "required": ["name"],
            "additionalProperties": False,
        },
    }


def load(agent, values):
    name = SKILLS[agent][0]
    if values != {"name": name}:
        raise ValueError("This skill is not available to this role.")
    return {
        "name": name,
        "instructions": (Path(__file__).parent / "agent_skills" / name / "SKILL.md").read_text(
            encoding="utf-8"
        ),
    }
