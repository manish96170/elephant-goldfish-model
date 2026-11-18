# Copyright 2026 Google LLC.
# SPDX-License-Identifier: Apache-2.0

"""Install an experimental OpenCode V2 bundle without changing user config."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
HOST_VERSION = "2.3.0"
REVIEWERS = (
    "codebase_details", "comprehension", "design_critic",
    "implementation_readiness", "inventive_catalyst", "structural", "style",
    "zoom_out",
)


def name(path: Path) -> str:
    """Read a canonical EGM name without a runtime YAML dependency."""
    header = path.read_text(encoding="utf-8").split("---", 2)[1]
    match = re.search(r"^name: (egm-[a-z-]+)$", header, re.MULTILINE)
    if not match:
        raise ValueError(f"Missing canonical name: {path}")
    return match[1]


def validate_destination(destination: Path) -> Path:
    """Reject unsafe output paths before creating files."""
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination = destination.resolve()
    if "\\" in destination.as_posix() or any(
        character in str(destination) for character in "*?[]{}!@`$\n\r"
    ):
        raise ValueError("Installation path contains template or glob characters")
    if ".env." in str(destination).lower():
        raise ValueError("Installation path matches the .env read rules")
    if destination.is_relative_to(ROOT):
        raise ValueError("Install outside the source tree")
    return destination


def reviewer_permissions(bundle: Path) -> list[dict[str, str]]:
    """Return deny-first V2 reviewer permissions.

    OpenCode V2 matches grep permissions against a search expression, not the
    target path. Keep grep denied so it cannot bypass .env read exclusions.
    """
    return [
        {"action": "*", "resource": "*", "effect": "deny"},
        {"action": "read", "resource": "*", "effect": "allow"},
        {"action": "read", "resource": "*.env", "effect": "deny"},
        {"action": "read", "resource": "*.env.*", "effect": "deny"},
        {"action": "read", "resource": "*.env.example", "effect": "allow"},
        {"action": "glob", "resource": "*", "effect": "allow"},
        {"action": "external_directory", "resource": "*", "effect": "deny"},
        {"action": "external_directory", "resource": f"{bundle}/*", "effect": "allow"},
    ]


def install(destination: Path) -> Path:
    """Create a new V2 candidate and return its configuration path."""
    destination = validate_destination(destination)
    destination.mkdir(parents=True)
    bundle = destination / "bundle"
    bundle.mkdir()
    for directory in ("skills", "agents", "resources", "docs"):
        shutil.copytree(ROOT / directory, bundle / directory)
    for filename in ("plugin.json", "LICENSE", "README.md", "TESTING.md"):
        shutil.copy2(ROOT / filename, bundle / filename)

    skills = destination / "skills"
    skills.mkdir()
    for skill in sorted((bundle / "skills").glob("*/SKILL.md")):
        (skills / name(skill)).symlink_to(skill.parent, target_is_directory=True)

    guide = bundle / "docs" / "opencode_v2.md"
    context = (
        f"Read {guide} first. EGM bundle root: {bundle}. "
        "Resolve agents/, resources/, and docs/ against this root. "
        "Resolve references/ against the canonical skill directory. "
        "Resolve user files and outputs against the project working directory. "
    )
    agents: dict[str, dict] = {}
    reviewer_ids = []
    for reviewer in REVIEWERS:
        persona = bundle / "agents" / f"{reviewer}.md"
        reviewer_id = name(persona)
        reviewer_ids.append(reviewer_id)
        agents[reviewer_id] = {
            "description": f"EGM read-only {reviewer} reviewer (experimental V2)",
            "mode": "subagent",
            "color": "#E86E00",
            "permissions": reviewer_permissions(bundle),
            "system": (
                context + f"Read {persona} before the target and supplied standards. "
                "Return findings to the caller. Do not write reports or delegate. "
                "Read prior reports only when explicitly supplied and required by the canonical stage. "
                "Do not retrieve unsolicited history, memory, or earlier reviewer findings. "
                "Report inaccessible required files as an incomplete review."
            ),
        }
    agents["egm"] = {
        "description": "EGM orchestrator (experimental OpenCode V2)",
        "mode": "primary",
        "color": "#1B6EF3",
        "permissions": [
            {"action": "*", "resource": "*", "effect": "ask"},
            {"action": "read", "resource": "*", "effect": "allow"},
            {"action": "read", "resource": "*.env", "effect": "ask"},
            {"action": "read", "resource": "*.env.*", "effect": "ask"},
            {"action": "read", "resource": "*.env.example", "effect": "allow"},
            {"action": "skill", "resource": "*", "effect": "deny"},
            {"action": "skill", "resource": "egm-*", "effect": "allow"},
            {"action": "subagent", "resource": "*", "effect": "deny"},
            *({"action": "subagent", "resource": reviewer_id, "effect": "allow"}
              for reviewer_id in reviewer_ids),
            {"action": "external_directory", "resource": "*", "effect": "ask"},
            {"action": "external_directory", "resource": f"{bundle}/*", "effect": "allow"},
        ],
        "system": (
            context + "Follow the canonical skill. Dispatch reviewers directly with subagent "
            "using the registered reviewer ID. Start a new subagent for every independent review; "
            "never resume a reviewer. Wait for completion. Pass only the task, absolute resource paths, "
            "target, standards, and selected reading list, not conversation history. Stop if delegation "
            "or a required completion is missing. When running brainstorm before draft, complete all "
            "seven brainstorm reviewers and synthesize their findings into concepts_brief.md before drafting. "
            "In review, write each completed stage report before starting the next stage. Before Step 8, "
            "verify zoom_out_report.md exists in the artifact directory and pass its absolute path to the "
            "reviewer; stop if it is missing. Write reports yourself. Preserve every human approval gate."
        ),
    }
    commands = {
        name(skill): {
            "description": f"Run {name(skill)} (experimental OpenCode V2)",
            "agent": "egm",
            "template": context + f"Read and execute {skill}.\nUser request: $ARGUMENTS",
        }
        for skill in sorted((bundle / "skills").glob("*/SKILL.md"))
    }
    config = {
        "$schema": "https://opencode.ai/config.json",
        "update": "disable",
        "default_agent": "egm",
        "skills": [str(skills)],
        "agents": agents,
        "commands": commands,
    }
    config_path = destination / "xdg" / "opencode" / "opencode.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    metadata = json.loads((bundle / "plugin.json").read_text(encoding="utf-8"))
    (destination / "installation.json").write_text(json.dumps({
        "name": metadata["name"], "version": metadata["version"],
        "host_version": HOST_VERSION, "status": "experimental",
        "sha256": {
            path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(bundle.rglob("*")) if path.is_file()
        },
    }, indent=2) + "\n", encoding="utf-8")
    return config_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New, fixed installation directory")
    print(install(parser.parse_args().destination))
