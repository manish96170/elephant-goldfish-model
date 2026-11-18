# Copyright 2026 Google LLC.
# SPDX-License-Identifier: Apache-2.0

"""Offline checks for the experimental OpenCode V2 installer."""

import hashlib
import json
import os
from pathlib import Path
import re
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = runpy.run_path(str(ROOT / "adapters/opencode-v2/install.py"))


def v2_match(pattern: str, value: str) -> bool:
    escaped = re.escape(pattern.replace("\\", "/")).replace(r"\*", ".*").replace(r"\?", ".")
    flags = re.S | (re.I if os.name == "nt" else 0)
    return re.fullmatch(escaped, value.replace("\\", "/"), flags) is not None


def effect(rules: list[dict[str, str]], action: str, resource: str) -> str | None:
    value = None
    for rule in rules:
        if v2_match(rule["action"], action) and v2_match(rule["resource"], resource):
            value = rule["effect"]
    return value


def test_install_preserves_resources_and_generates_v2_contract(tmp_path: Path) -> None:
    destination = tmp_path / "EGM candidate ü"
    config_path = ADAPTER["install"](destination)
    config = json.loads(config_path.read_text())
    identity = json.loads((destination / "installation.json").read_text())
    canonical = json.loads((ROOT / "plugin.json").read_text())

    assert (identity["name"], identity["version"]) == (canonical["name"], canonical["version"])
    assert identity["host_version"] == "2.3.0"
    assert identity["status"] == "experimental"
    assert config_path == destination / "xdg/opencode/opencode.json"
    assert config["update"] == "disable"
    assert config["default_agent"] == "egm"
    assert set(config).isdisjoint({"agent", "command", "permission", "autoupdate"})
    assert len(config["commands"]) == len(list((ROOT / "skills").glob("*/SKILL.md")))

    for relative, digest in identity["sha256"].items():
        installed = destination / relative
        source = ROOT / installed.relative_to(destination / "bundle")
        assert installed.read_bytes() == source.read_bytes()
        assert hashlib.sha256(installed.read_bytes()).hexdigest() == digest

    bundle = destination / "bundle"
    assert Path(config["skills"][0]) == destination / "skills"
    for skill in (ROOT / "skills").glob("*/SKILL.md"):
        identifier = ADAPTER["name"](skill)
        alias = destination / "skills" / identifier
        assert alias.resolve() == bundle / "skills" / skill.parent.name
        assert config["commands"][identifier]["agent"] == "egm"
        assert str(bundle / "skills" / skill.parent.name / "SKILL.md") in config["commands"][identifier]["template"]

    reviewer_ids = {ADAPTER["name"](bundle / "agents" / f"{item}.md") for item in ADAPTER["REVIEWERS"]}
    assert set(config["agents"]) == {"egm", *reviewer_ids}
    for reviewer_id in reviewer_ids:
        reviewer = config["agents"][reviewer_id]
        assert reviewer["mode"] == "subagent"
        assert reviewer["permissions"][0] == {"action": "*", "resource": "*", "effect": "deny"}
        assert effect(reviewer["permissions"], "read", "src/app.py") == "allow"
        assert effect(reviewer["permissions"], "read", ".env") == "deny"
        assert effect(reviewer["permissions"], "read", "app/.env.production") == "deny"
        assert effect(reviewer["permissions"], "read", "app/.env.example") == "allow"
        assert effect(reviewer["permissions"], "glob", "**/*.py") == "allow"
        for action in ("grep", "edit", "shell", "webfetch", "websearch", "skill", "subagent"):
            assert effect(reviewer["permissions"], action, "*") == "deny"
        assert effect(reviewer["permissions"], "opencode_read_mcp_resource", "server:uri") == "deny"
        assert effect(reviewer["permissions"], "external_directory", "/other/path/*") == "deny"
        assert effect(reviewer["permissions"], "external_directory", f"{bundle}/agents/*") == "allow"

    primary = config["agents"]["egm"]
    assert primary["mode"] == "primary"
    assert effect(primary["permissions"], "subagent", "other") == "deny"
    for reviewer_id in reviewer_ids:
        assert effect(primary["permissions"], "subagent", reviewer_id) == "allow"
    assert "Start a new subagent" in primary["system"]
    assert "never resume a reviewer" in primary["system"]


def test_existing_destination_is_untouched(tmp_path: Path) -> None:
    sentinel = tmp_path / "existing.txt"
    sentinel.write_text("other worker")
    with pytest.raises(FileExistsError):
        ADAPTER["install"](tmp_path)
    assert list(tmp_path.iterdir()) == [sentinel]


@pytest.mark.parametrize("suffix", ["bad*", "bad?", "bad[glob]", "{env:HOME}", "bad\npath", r"bad\path"])
def test_unsafe_destination_is_rejected(tmp_path: Path, suffix: str) -> None:
    if "\\" in suffix and Path(suffix).name != suffix:
        pytest.skip("Requires a literal backslash in a POSIX filename")
    with pytest.raises(ValueError):
        ADAPTER["install"](tmp_path / suffix)
    assert not list(tmp_path.iterdir())


def test_env_matching_destination_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=".env"):
        ADAPTER["install"](tmp_path / "staging.env.candidate")
