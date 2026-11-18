<!-- Copyright 2026 Google LLC. SPDX-License-Identifier: Apache-2.0 -->

# OpenCode V2 integration (experimental)

This adapter targets OpenCode CLI **2.3.0** and V2 `agents`, `permissions`,
`commands`, and `subagent` interfaces. It is experimental. Installation and
the scripted native probe do not establish full workflow support or complete
reviewer isolation.

## Install

Use Python 3.10+ and a POSIX filesystem with symbolic links. Select a fixed
candidate commit and install outside the source tree:

```sh
git rev-parse HEAD
python3 adapters/opencode-v2/install.py /absolute/egm-opencode-v2-candidate
opencode --version
```

Inspect the generated `xdg/opencode/opencode.json` and `installation.json` before use. The
candidate does not modify global or project OpenCode configuration. It records
SHA-256 hashes for every copied runtime file.

Start OpenCode from the project directory with the explicit candidate config:

```sh
XDG_CONFIG_HOME=/absolute/egm-opencode-v2-candidate/xdg opencode --standalone --agent egm
```

Use an ordinary message to select a skill, for example:

```text
Use the egm-review skill to review /absolute/path/design.md.
```

Do not paste untrusted material into slash-command arguments. Command argument
interpolation requires separate verification for each supported OpenCode V2
release. Save untrusted material in a project file and name that file instead.

## Dispatch and permissions

Goldfish reviewers use fresh OpenCode V2 `subagent` sessions. The `egm` agent
starts a new reviewer for every independent task and must not resume a prior
reviewer. It passes only the task, selected source paths, standards, target,
and explicitly required prior reports. It does not pass parent conversation
history, memory, rationale, or unrelated findings.

Reviewers have deny-first permissions. They may use only `read` and `glob` on
project files, plus the installed bundle. They cannot use edits, shell, web
access, MCP resources or tools, skills, or child delegation. `.env` and
`.env.*` reads are denied; `.env.example` remains readable.

`grep` is also denied. In OpenCode V2 its permission resource is the regular
expression rather than the searched path, so it cannot safely enforce the
`.env` file boundary.

A fresh child session does not prove complete isolation. OpenCode can inject
user or project `AGENTS.md` instructions, and reviewers share the project
filesystem. The adapter tells reviewers not to read unsolicited history,
memory, or prior reports, but this is not an enforcement guarantee. Review
only the smallest required project reading list and record these limits with
any evidence.

## Verification limits

Run the offline installer and unit checks before a live model test. The native
probe uses a scripted local model and must record installation, child dispatch,
required persona reads, secret-read denial, and actual child tools separately.
A passing probe does not establish review quality, human approval pauses,
complete context isolation, process isolation, filesystem isolation, or
behavior on a different OpenCode version.

EGM has no runtime telemetry endpoint, hosted service, database, analytics
client, or separate account. The selected OpenCode provider processes the
prompts and project files supplied for a review under its own settings.
