# CodeAgentArc

A Python 3.12 coding agent that turns architecture documentation and UML views
into a runnable repository. It reads the source material, writes files, runs
checks, and revises its work through an explicit model/tool/result loop.

## Quick Start

### 1. Run the Code Agent

Prerequisites: Git and Python 3.12 or newer with Tkinter available. The agent
itself is cross-platform; a live generation also needs an OpenAI or Gemini API
key. Clone and enter the repository:

~~~sh
git clone https://github.com/ShaheerAhmed3/CodeAgentArc.git
cd CodeAgentArc
~~~

On macOS/Linux, create the environment and install the OpenAI-enabled agent:

~~~sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,openai]'
cp .env.example .env
~~~

On Windows PowerShell:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,openai]"
Copy-Item .env.example .env
~~~

Edit `.env` and set `OPENAI_API_KEY` to your key. Do not commit `.env`. To use
Gemini instead, install `.[dev,gemini]`, set `GEMINI_API_KEY`, and select the
Gemini provider.

Normalize the supplied architecture inputs (optional, useful for inspection),
then generate a fresh desktop-game repository:

~~~sh
python -m code_agent.cli normalize --output generated/architecture.json
python -m code_agent.cli generate --output generated/space-fractions-run --provider openai --model gpt-5 --max-turns 40
~~~

The generation command consumes
`architecture/inputs/Architecture_Documentation.md` and
`architecture/inputs/Architecture_View.md` by default. Output directories must
be absent or empty, so choose a new name for each run. A successful run ends
with deterministic desktop-game validation and writes details under
`generated/space-fractions-run/.codeagent/`.

### 2. Run the Generated Game

For the fresh output created above:

~~~sh
cd generated/space-fractions-run
python main.py
~~~

The game opens as a local desktop window; no browser or server is required. The
checked-in generated example can be launched directly from the repository root:

~~~sh
cd generated/space-fractions
python main.py
~~~

If `import tkinter` fails, install the Tk support package matching your Python
distribution, then rerun the same command. On Debian/Ubuntu this is commonly
`python3-tk`; the standard Windows python.org installer includes Tcl/Tk.

### 3. Run Tests

Run the Code Agent test suite from the repository root with its virtual
environment activated:

~~~sh
python -m pytest -q
~~~

Run the checked-in generated game's headless domain tests separately:

~~~sh
cd generated/space-fractions
python -m pip install -r requirements.txt
python -m pytest -q
~~~

Gemini and OpenAI are optional real adapters, using their official Python SDKs.
Neither provider is fundamental to the runtime: AgentLoop depends on LLMProvider,
and a deterministic MockProvider exercises the same pipeline offline.

## Inputs and example project

`architecture/inputs/Architecture_Documentation.md` and
`architecture/inputs/Architecture_View.md` describe Space Fractions, the
example application in this repository. These are the generator's two input
files. Tests pin their SHA-256 hashes so the example remains reproducible.

Normalization extracts project information, components, technology/contracts,
schemas, deployment/security/testing information, assumptions, documentation
sections, and 13 PlantUML blocks across 11 numbered entries. Source text and
hashes remain in the exported JSON. Unrecognized content is retained; parsing
does not silently correct architecture statements or interpret UML semantics.

## How it works

~~~text
Architecture Markdown + UML
  -> deterministic normalization -> structured context
  -> LLMProvider -> model-selected tool calls -> tool execution
  -> observations returned to the model -> inspect/edit/test again
  -> finish + final response -> deterministic validation -> report
~~~

This is an iterative agent: it can read real files, observe test failures, edit
the implementation, and rerun checks. It does not ask the model to return a
repository as one giant Markdown response. The generation prompt requires
source fidelity, a coherent minimum implementation, documented decisions,
inspection before edits, and verification before completion. For this evaluation,
the explicit desktop constraint overrides incompatible web deployment suggestions
in the source: the generated game must be a local GUI, preferably Python/Tkinter,
and backend-only or browser-only outputs fail validation.

## Setup and offline tests

Prerequisites are Python 3.12 or newer with Tkinter, and Git. Run the
commands from the repository root.

### macOS

~~~sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,openai]'
python -m pytest -q
~~~

If `python3.12` is unavailable and you use Homebrew, install it with
`brew install python@3.12`.

### Windows PowerShell

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,openai]"
python -m pytest -q
~~~

Install `.[dev,gemini]` instead for Gemini, or `.[dev,gemini,openai]` for
both providers. After activation, the remaining Python commands are the same on
macOS and Windows.

Installation needs package access; tests need neither network nor credentials.
The normal test process blocks network connections, and Gemini tests fake the
SDK client. Installing without the gemini extra supports normalization/mock use
and skips SDK-specific tests.

## Configuration

Create a local `.env` from `.env.example` and fill in only the provider key you
intend to use. The application reads this file but never creates or overwrites it.
Its safe template is:

~~~dotenv
CODE_AGENT_PROVIDER=gemini
CODE_AGENT_MODEL=gemini-3.8-flash
GEMINI_API_KEY=
OPENAI_API_KEY=
~~~

Populate the selected provider's key locally before a live run. Never put it in source or a CLI
argument. Configuration precedence is CLI provider/model overrides, process
environment, current-directory .env, then defaults. A blank environment key
overrides the file too; remove that variable if you want the file's value.
Missing/blank keys fail before output creation or client initialization.

python-dotenv reads values without injecting them into the process environment.
The adapter receives the key privately; it is not included in prompts, reports,
or trace configuration. The included .env.example contains only placeholders.

## Commands

Export normalized JSON to a new filename:

~~~sh
python -m code_agent.cli normalize --output generated/architecture.json
~~~

Existing output files are refused. Choose another filename if this export
already exists. Without --output, JSON is written to stdout.

After configuring `OPENAI_API_KEY` locally, generate one repository:

~~~sh
python -m code_agent.cli generate --output generated/space-fractions-2 --provider openai --model gpt-5 --max-turns 40
~~~

The installed `code-agent generate` entry point accepts the same options.
For Gemini, set `GEMINI_API_KEY` and use `--provider gemini --model gemini-3.8-flash`.
The checked-in example used `--max-turns 40`. CLI
provider/model flags override the values in `.env`; switching providers without
an explicit model uses that provider's default rather than the other provider's
configured model. The default
OpenAI model is `gpt-5`; choose an account-accessible model explicitly if needed.
Defaults permit the shorter `code-agent generate --output generated/space-fractions`
form when running from this project directory.

Output must be an absent or empty project subdirectory under generated/.
The repository root, generated/ itself, linked paths, and nonempty directories
are rejected. There is no force, deletion, or resume option. Use a fresh path,
such as generated/space-fractions-2, for another attempt.

Generation accepts Markdown inputs. Importing a normalized --spec is deferred;
the normalized model is still the basis for every generation context. Topic
fields reference sections, and duplicate whole-source text is omitted from
the prompt while all sections and PlantUML blocks remain available.

## Run the checked-in Space Fractions example

The generated example uses Python and Tkinter. Its domain and question logic are
separate from the GUI, so tests run without opening a window.

### macOS

~~~sh
cd generated/space-fractions
python -m pip install -r requirements.txt
python -m pytest -q
python main.py
~~~

### Windows PowerShell

~~~powershell
cd generated/space-fractions
python -m pip install -r requirements.txt
python -m pytest -q
python main.py
~~~

The tests cover fraction-question selection, answer validation, scoring,
progression, and game completion. See the
[Space Fractions README](generated/space-fractions/README.md) for gameplay and
the mapping from the web-oriented source architecture to the local desktop runtime.

## Providers and tools

The factory supports gemini, openai, and mock. Adding another provider means implementing
an adapter and adding a factory branch. No vendor SDK objects enter the loop,
tools, workspace, or validator.

GeminiProvider sends function declarations and explicitly disables SDK automatic
function calling. OpenAIProvider uses Responses function calls and sends their
results back as `function_call_output` items. Our loop executes tools for both.
Adapters preserve call IDs and private continuation state. SDK errors become
concise application errors with safe status/category fields in the report, never
raw response bodies. Each request has a 120-second timeout and no automatic retry.

| Tool | Input and behavior |
| --- | --- |
| read_file | path; optional inclusive 1-based start_line/end_line |
| write_file | path, content; creates parents; overwrite defaults to false |
| edit_file | path, old_text, new_text; one exact match required unless replace_all=true |
| list_files | optional directory, recursive, max_results; ordered files/directories |
| search_files | query; optional directory, pattern, case_sensitive, max_results |
| run_command | command argument list; optional timeout and verification flag |
| finish | summary; optional tests_run, assumptions, warnings string lists |

Filesystem tools enforce Workspace, reject escaping paths, and skip links during
traversal. Defaults cap files at 1,000,000 bytes, observations at 16,000 characters,
and listings/searches at 200 results. Expected failures become correlated error
observations rather than uncaught exceptions. Exact editing preserves other bytes.

Commands use shell=False, workspace cwd, and noninteractive stdin. Generation
configures a 120-second command timeout; each returned output stream is capped
at 16,000 bytes. Direct library use defaults to 30 seconds. Windows .bat/.cmd
launchers are rejected because Windows can invoke a shell implicitly; use node
or another executable with the relevant script path.

**Commands are not an OS/container sandbox.** Generation removes environment
variables with credential-like names or values containing the configured key,
but commands can still access external files/networks or spawn children.
The timeout terminates the direct child, not necessarily descendants. Temporary
file capture bounds Python memory, not disk usage. Filesystem checks do not
defend against hard links or concurrent directory replacement. Use trusted work.

## Validation, reports, and trace

Validation checks repository contents, README, an accepted dependency manifest,
recognized application source, tests or a test directory, and nonempty required
files. Generation and post-run verification additionally require evidence of a
local desktop GUI framework, a documented executable entry point, no browser or
localhost launch dependency, core game-flow behavior, exact launch/test commands,
and non-interactive domain tests. `ValidationPolicy` keeps those desktop checks
optional for independent generic uses of the validator. Docker is optional.

Generation additionally requires actual run_command evidence marked
verification=true after the last write/edit attempt or ordinary command.
These operations invalidate older checks because they may modify files.
Repeating the identical verification argument list replaces its previous result;
all distinct final checks must pass. Intermediate failures remain in the trace.
Python subprocesses disable bytecode writes to avoid stale imports during repairs.

The validator uses bounded source and documentation heuristics; it does not prove
UI quality, fully interpret code, parse manifests, or authenticate command results.
The prompt asks for genuine domain tests and a safe import/compile check. `finish`
records claims; validation and normal loop completion determine `GenerationReport.success`.

If the model writes documentation after its last verified test, the initial report
correctly fails because that evidence is stale. Recheck the final files with:

~~~text
code-agent verify --output generated/space-fractions --command python -m pytest -q
~~~

This runs the command from the generated repository, repeats structural validation,
and updates the report while preserving `initial_validation` and `initial_success`.
The trace appends a separate `post_run_verification` event; it does not pretend the
agent ran another tool call. Commands still run with host privileges, so use only
trusted generated projects.

Each started run produces:

~~~text
.codeagent/generation_report.json   provider/model, outcome, summaries, checks, command status
.codeagent/run.jsonl                turns, tool names/IDs, paths, content sizes, exit status
~~~

Reports cover normal completion, turn exhaustion, and caught provider/runtime
failures. Input/configuration rejection creates no run. Filesystem tools cannot
access the reserved .codeagent directory, which is excluded from validation.
Commands could still tamper with artifacts; reports are not signed evidence.
Deleted/inaccessible output directories can prevent persistence.

No full transcripts, write/edit contents, command arguments, output bodies,
environment dumps, or hidden reasoning are persisted. Summaries are bounded,
and the configured key is redacted from persisted strings. Detailed observations
exist in memory for the model. Continuation signatures never enter disk artifacts.

| Exit code | Outcome |
| --- | --- |
| 0 | Agent completed and validation passed |
| 1 | Agent completed but validation failed |
| 2 | Invalid arguments, configuration, or output target |
| 3 | Maximum turns reached |
| 4 | Provider/API failure |
| 5 | Runtime or input/output failure |

## Library use and project layout

Tests in tests/integration/test_generation.py demonstrate injecting a finite
mock response script into generate(...). Tests also exercise an initial failed
test, exact edit, and successful rerun. CLI --provider mock without a script
creates no application and deliberately fails validation; it is a wiring check.

~~~text
src/code_agent/
  cli.py, config.py       commands and provider configuration
  generation.py           composition and output safety
  reporting.py            redacted JSON/JSONL persistence
  agent/                  neutral models, loop, prompts, GenerationReport
  architecture/           source extraction and normalization
  providers/              protocol, factory, mock, Gemini/OpenAI adapters
  tools/                  registry and seven concrete tools
  workspace/              filesystem boundary and traversal
  validation/             deterministic checks and ValidationReport
architecture/inputs/      versioned architecture source documents
tests/unit/, tests/integration/
docs/DESIGN.md             engineering reasoning and references
generated/space-fractions/  checked-in demonstration output
generated/                other runs and normalization exports are ignored
~~~

The checked-in Space Fractions example was freshly generated with the OpenAI
adapter after desktop requirements were added to the prompt. The normal generation
workflow completed in 30 turns with 29 tool calls and passed the desktop checks.
It includes an animated intro, main menu, playable fraction flow, pause/resume,
score and help screens, exit controls, and an admin question editor. A focused
Code Agent repair pass corrected macOS frame layout and wrong-answer feedback; no
game code was hand-edited. Four headless tests, compilation, Tkinter launch, and
independent final validation passed. The
[generated README](generated/space-fractions/README.md) maps web/cloud source
guidance to local modules and JSON persistence and documents demo limitations.

Parser recognition is tailored to the source conventions. Context compaction, input
token budgets, resumable runs, --spec import, and process isolation are deferred.
There is no multi-agent orchestration, database, server, or agent framework.
See [DESIGN.md](docs/DESIGN.md) for the dependency boundaries and research.
