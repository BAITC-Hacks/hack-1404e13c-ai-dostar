# Shared memory setup

The shared baseline is [`team-memory.md`](team-memory.md). It is available to every teammate after pulling the repository. Mem0 adds automatic capture and semantic search across Codex sessions.

## One-time setup for each teammate

1. Install Codex and make Python 3.10+ available as `python3`.
2. From this repository, run `./scripts/setup-memory.sh`. It installs the official Mem0 Codex plugin, including its MCP search tool, skills, and lifecycle hooks.
3. Obtain access to the **same Mem0 account/workspace** as the rest of the team. Store its API key privately as `MEM0_API_KEY` in the environment that launches Codex. Never commit the key or paste it into team memory. A personal Mem0 account will create a separate memory silo, even with the same Git remote.
4. Restart Codex. Review and trust the plugin's hooks if Codex prompts for it. Ask Codex to run Mem0 status/doctor; `mem0_authentication` should pass.

Codex derives the shared repository identity from the Git remote. Keep `origin` pointed at `https://github.com/BAITC-Hacks/hack-1404e13c-ai-dostar.git` or its SSH equivalent. Each teammate should use a distinct `MEM0_CODE_USER_ID` (the plugin can derive one by default); the plugin uses the shared project lane for repository memories and keeps personal preferences separate. Search the plugin's `repo` scope to recall both shared project decisions and your own preferences.

The project `.codex/config.toml` declares the Mem0 marketplace and enables the plugin for trusted local checkouts. The setup script also installs it in each person's Codex installation. Do not register the direct Mem0 MCP server separately: the plugin already provides it.

## What to remember

- Put stable decisions, verified commands, interface contracts, and unresolved blockers in `team-memory.md` during the task. Review the Git diff before sharing it.
- Use Mem0 for relevant past discussions and task history. Verify retrieved claims against the repository before using them.
- Exclude credentials, personal information, and large raw logs from both shared memory paths.

## Account ownership

The first local Mem0 CLI account was created in Agent Mode and is currently unclaimed. The owner can claim it without losing its key or memories by running `mem0 init --email <your-email>` in their terminal. Arrange access to the same Mem0 workspace for teammates through the Mem0 account controls or a private credential channel; the repository contains no key.
