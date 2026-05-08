## Relationship to upstream

This is a Windows 11 fork of [imkunal007219/claude-coworker-model](https://github.com/imkunal007219/claude-coworker-model).
Differences from upstream:
- Windows-only (`setup.ps1`, `.cmd` shims, UTF-8 stdout fix for cp1252).
- Provider profiles in `config.py` instead of `WORKER_*` environment variables.
- Adds DeepSeek V4 Flash/Pro alongside Kimi and Ollama.
- DeepSeek V4 Flash as default.

For Linux/macOS, use the upstream repo.

# Claude Coworker Model

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Offload bulk I/O from Claude Code to cheap LLMs. Save thousands of tokens on file reading, 
boilerplate generation, and doc updates. Worker calls cost ~$0.02; primary model focuses on architecture.

## Quick Start (Windows 11)

Run from a normal PowerShell window:

```powershell
git clone https://github.com/imkunal007219/claude-coworker-model.git
cd claude-coworker-model
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup.ps1` creates an isolated venv at `%LOCALAPPDATA%\claude-coworker\venv`, installs `openai`, and drops `.cmd` 
launcher shims into `%USERPROFILE%\.local\bin` (added to your User PATH if missing).

Then paste your API key into the `api_key` field of the relevant provider in [config.py](config.py).

Test:
```powershell
coworker-config show
ask --paths setup.ps1 --question "what does this script do?"
```

## CLAUDE.md Setup
Needed to make Claude Code Desktop use this automatically:

For ALL projects: 
Add the content of the `CLAUDE.md.template` file to your main `CLAUDE.md` file so Claude Code loads it automatically on startup.

Per project:
Copy the content of the `CLAUDE.md.template` file to your `CLAUDE.md` file at the project root. 
If you do not want it automatically for each project. Or different workers for different projects.


## How It Works

The expensive model (Claude) handles reasoning and architecture. The cheap worker model handles token-heavy I/O:

1. **Read**: Worker ingests large codebases, returns structured summaries with file paths and line numbers
2. **Generate**: Worker produces boilerplate using existing files as style references
3. **Extract**: Worker parses session transcripts for documentation

Pattern: Claude decides *what* to do; the worker does the *reading/writing*.

## Configuration — `config.py`

Provider profiles live in [config.py](config.py). 
The default active provider is **DeepSeek V4 Flash**. 
Switch any time:

```bash
coworker-config list                  # show all providers and the active one
coworker-config show                  # show the resolved active config
coworker-config use deepseek-v4-pro   # switch active provider
coworker-config use kimi
coworker-config use ollama
```

Built-in profiles:

| Name                | Provider                      | Model                |
|---------------------|-------------------------------|----------------------|
| `deepseek-v4-flash` | DeepSeek V4 Flash *(default)* | `deepseek-v4-flash`  |
| `deepseek-v4-pro`   | DeepSeek V4 Pro               | `deepseek-v4-pro`    |
| `kimi`              | Kimi (Moonshot AI)            | `kimi-k2.5`          |
| `ollama`            | Ollama (local)                | `qwen2.5-coder:14b`  |

API keys are stored in the `api_key` field of each provider in [config.py](config.py). Paste your key in directly — no env vars required.

### Adding a new provider

Edit [config.py](config.py) and add an entry to `PROVIDERS`:

```python
"my-provider": {
    "label": "My Provider",
    "base_url": "https://api.example.com/v1",
    "model": "some-model",
    "api_key": "sk-...",
},
```

Any OpenAI-compatible endpoint works.

## Tools

### ask — bulk reading
Delegate bulk reading to the worker model. Returns structured bullets, not prose.

```bash
ask \
  --paths auth.py database.py utils.py \
  --question "Identify all unvalidated inputs" \
  --max-tokens 8192
```

Flags:
- `--paths`: Files to ingest
- `--question`: Specific extraction query
- `--max-tokens`: Total budget including reasoning tokens (default 8192)
- `--provider`: Override active provider for this call
- `--model`: Override model id

### write — boilerplate generation
Generate code or documentation using an existing file as a style reference.

```bash
write \
  --spec "Write pytest tests for auth.py covering OAuth2 flow" \
  --context tests/test_main.py \
  --target tests/test_auth.py
```

Flags:
- `--spec`: What to write
- `--context`: Reference file to mimic (style, imports, structure)
- `--target`: Output file path
- `--max-tokens`: Token budget for reasoning + output (default 16384)
- `--provider`, `--model`: Same as `ask`

### extract-chat — chat transcript extraction
Convert Claude Code JSONL session logs to human-readable text. Stdlib only — works regardless of which provider is active.

```bash
# Extract last session to stdout
extract-chat ~/.claude/projects/my-project/session.jsonl

# Write to file
extract-chat session.jsonl -o chat.txt

# Pipe to ask for doc updates
extract-chat session.jsonl -o chat.txt && \
  ask --paths chat.txt docs/README.md --question "What doc updates are needed?"
```

### coworker-config — switch providers
Already covered above. Subcommands: `list`, `show`, `use <name>`.


## Windows 11 + Claude Code Desktop notes

- The Windows installer puts `.cmd` shims in `%USERPROFILE%\.local\bin` and adds that folder to your User PATH if needed. 
  Open a **new** terminal after first install for PATH changes to take effect.
- The venv lives at `%LOCALAPPDATA%\claude-coworker\venv`.
- Run setup from a normal PowerShell window. Don't run `setup.ps1` from inside Claude Code Desktop — its sandbox redirects `%LOCALAPPDATA%` 
  so the venv lands in a hidden per-app folder regular shells can't see. 

## Results

| Metric                  |Before                | After                 |
|-------------------------|----------------------|-----------------------|
| Claude Pro weekly limit | Hit by Wednesday     | Never hit             |
| Token usage per session | 80%+ on file reading | 20% (summaries only)  |
| 3-week worker API cost  | —                    | $0.38 total           |
| Context window usage    | 80% reading files    | 20% reading summaries |

Based on the pattern described in [this implementation (medium link)](https://medium.com/@kunalbhardwaj598/i-was-burning-through-claude-codes-weekly-limit-in-3-days-here-s-how-i-fixed-it-0344c555abda) [Reddit link](https://www.reddit.com/r/ClaudeAI/comments/1t1o43w/i_gave_claude_code_a_002call_coworker_and_stopped/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button) (567K views Reddit, 7.2K Medium).

## Author
Original:
**Kunal Bhardwaj** — Systems engineer working on autonomous drones and AI-powered developer tools. Building at the intersection of embedded systems and LLM workflows.

- Blog: [medium.com/@kunalbhardwaj](https://medium.com/@kunalbhardwaj598/i-was-burning-through-claude-codes-weekly-limit-in-3-days-here-s-how-i-fixed-it-0344c555abda)
- LinkedIn: [linkedin.com/in/kunalbhardwaj](https://www.linkedin.com/in/kunal-bhardwaj-61433818b)

Windows 11 only version:
**Jan Mantkowski** — Project Manager working on Windows apps for panoramic streetview footage recorded by 360 cameras.

- Website: https://www.360camsters.com

## Contributing

PRs welcome. Focus areas: additional provider templates, token usage optimization, and extracting structured data from more session formats.

MIT License. See [LICENSE](LICENSE).
