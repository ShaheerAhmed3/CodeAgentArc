# Design

## Agent mechanism and research

The central mechanism is a feedback loop: construct context, ask the model for
an action, execute tools, append observations, and ask again. This lets a future
coding agent inspect existing files and react to failing tests. A one-shot text
generation script cannot observe the repository or verify that its code works.

The assignment's three research links were reviewed on 2026-09-21:

- [Anthropic's Claude Code repository](https://github.com/anthropics/claude-code)
  is the official public project entry point. Its presence on GitHub is not
  evidence that all implementation internals are available under an open-source
  license; this implementation makes no claim to reproduce private internals.
- [Claw Code](https://github.com/ultraworkers/claw-code) currently describes a
  Rust CLI harness and points to `rust/` as its canonical implementation, with
  a companion Python/reference workspace. Its broader surface is outside this
  foundation's scope; no source code was copied.
- [How Claude Code works](https://github.com/Windy3f3f3f3f/how-claude-code-works)
  is a third-party analysis resource, not an authoritative runtime contract.

The primary mechanism reference is Anthropic's
[agentic loop documentation](https://code.claude.com/docs/en/how-claude-code-works):
context gathering, action, and verification recur, with tool results informing
subsequent decisions. The implementation here adopts that public mechanism,
not the full product's orchestration, persistence, or permission systems.

## Responsibility boundaries

Python 3.12 provides dataclasses, protocols, JSON, regular expressions, and
filesystem APIs without runtime dependencies. This keeps the core inspectable
and makes offline tests straightforward. python-dotenv handles development
configuration; google-genai and openai are optional provider dependencies. pytest is limited
to development.

`architecture` extracts source information deterministically before model use.
The Markdown scanner handles ATX headings and backtick/tilde fences and does
not treat headings inside code blocks as document structure. Recognized heading
paths index excerpts by topic. Components come from explicit overview bullets;
the project name and style use source-specific labels/sentence patterns.
These are extraction rules, not semantic inference or a general Markdown parser.

The normalized document stores complete source text and hashes, ordered
sections with heading paths, and individually preserved PlantUML payloads.
Section text normalizes BOM/newlines; source text and UML payloads retain their
original characters. JSON has stable ordering, no timestamp, and no absolute
paths. Each excerpt points to a section. Numbered captions may describe multiple
diagrams, so diagram number is not used as a unique key. Malformed fences fail
explicitly; missing UML markers produce warnings while retaining the payload.

The source's microservices, infrastructure choices, SLO/error-budget statements,
traceability filenames, and AdminComponent diagram content are retained as
written. We do not invent missing component contracts or resolve contradictions.
`assumptions` means explicit source assumptions; `agent_assumptions` and
`implementation_decisions` are separate, initially empty fields. `warnings`
records extraction limits, not invented requirements. Whole-source retention
also covers content that the topic index does not recognize.

`agent.models` defines messages, tool definitions, calls, results, and model
responses. `LLMProvider` is a structural protocol; adapters translate external
request/response formats and preserve call IDs. Only the composition layer
selects an adapter and model. No SDK types enter parsing, tools, or the loop.
MockProvider copies its script, records isolated requests, and raises on script
exhaustion instead of silently manufacturing a successful answer.

`AgentLoop` only coordinates these contracts. It records the assistant's calls
before their observations, dispatches multiple calls in order, and counts one
provider completion as one turn. Calls on the last allowed turn still execute
and remain in the returned transcript, but no further provider request occurs.
`max_turns` returns an explicit incomplete result with no final answer. Empty or
duplicate call IDs are rejected before dispatch. Provider failures propagate.

`ToolRegistry` prevents duplicate registrations and converts unknown tools,
expected argument errors, and filesystem errors into correlated error results.
Tools own argument validation; schemas describe inputs to providers but are
not automatically enforced by a full JSON Schema engine. Unexpected programming
errors propagate instead of being hidden as ordinary model mistakes. Concrete
tools return `ToolOutput` (text, error flag, optional metadata/completion), and
the registry attaches call identity to form the existing `ToolResult`. Returning
plain text remains supported, preserving Stage 1 tools and tests.

`Workspace.resolve` accepts relative paths and checks the resolved target is
beneath its canonical root. It rejects parent traversal, absolute/drive/UNC
paths, alternate data streams, device names, and ambiguous Windows names, even
when running on another OS. Existing escaping symlinks/junctions are rejected.
The configured root is trusted. The caller must use the returned path for every
filesystem operation. This boundary does not contain subprocesses or defend
against hard links and concurrent filesystem replacement races.

## Small coding tools

The five filesystem tools share cohesive UTF-8 and size-limit helpers in
`tools/filesystem.py`. Their arguments and behaviors are explicit: read a file,
create a file, replace exact text, list entries, or find a substring. There is no
patch language, AST machinery, shell-based file editing, or extra model call.
Every requested and discovered path goes through Workspace. Traversal is sorted
per directory, visits directory entries before descendants, and skips symlinks
and junctions, including internal cycles. Explicit paths may resolve internal
links safely; an escaping target always fails.

Creation uses exclusive file opening by default. An existing file requires
`overwrite=true`. Edits require existing UTF-8 text and exactly one non-overlapping
match unless `replace_all=true`. Empty/missing/ambiguous old text is rejected
before writing. Byte decoding/encoding preserves BOM and newline characters
outside the replacement. Writes are not transactional, and this stage does not
claim recovery from disk-full errors or races with external writers.

Files are capped at 1,000,000 bytes by default; oversized reads/edits fail instead
of editing a partial view. Read observations support inclusive 1-based lines.
Filesystem observations cap text at 16,000 characters plus a truncation marker.
Listings/searches cap results at 200, configurable by the host and reducible by
the model. Search skips unreadable, non-UTF-8, NUL-containing, or oversized files,
and returns a bounded snippet around the match. Globs match case-sensitively
against either the basename or workspace-relative POSIX path using fnmatch;
substring case sensitivity is a separate option. Search does not have a total
scan-time budget or implement gitignore filtering.

`run_command` uses an executable argument list, `shell=False`, workspace-root
cwd, and DEVNULL stdin. Nonzero exits, timeouts, and missing executables produce
error observations with structured metadata. Its host-configured timeout is
also the maximum accepted per-call timeout. Stdout and stderr are captured in
temporary files and only bounded prefixes are decoded, avoiding unbounded Python
memory from verbose commands. Invalid UTF-8 output uses replacement characters.
This limits returned output, not temporary disk usage. Timeout handling kills
and waits for the direct child; descendant process cleanup is not guaranteed.
Windows batch launchers are rejected because they can trigger implicit shell
execution. Invoke the underlying interpreter and script for such tools.

Neither `shell=False` nor workspace cwd provides OS-level isolation. A command
can read/write outside the workspace, use the network, or spawn children.
Generation supplies an environment with credential-like variables removed;
direct command-tool use inherits the environment unless one is supplied.
This does not isolate credentials stored elsewhere. The runtime assumes trusted local execution;
it has no elaborate command policy or container layer. The command runner remains
language-neutral and does not hard-code pytest or Node.js.

`finish` records `CompletionInfo` (summary, claimed tests, assumptions, warnings)
without stopping the loop specially. Its observation asks for a final response.
This preserves the original completion contract and handles a turn containing
multiple calls normally. The latest recorded completion is available from
AgentResult; it is a model declaration, not proof of successful verification.
Tool-call count records dispatches during this run, including error observations;
prior input history is not counted.

## Validation and scope

Tests exercise exact source preservation, topic extraction, repeated UML
captions, deterministic JSON, path traversal and escaping links, tool errors,
conversation ordering, multiple turns, turn exhaustion, and mock isolation.
Integration tests retain the original normalization/prompt checks and now exercise
real write/read/command/finish tools through MockProvider. One script produces
a tiny Python repository and runs its unittest suite offline. Command tests cover
exit status, cwd, literal arguments, truncation, and timeout output. SHA-256
checks continue to guard all three professor originals.

A no-tool response only means the model stopped requesting actions. The caller
runs `validate_repository` after the loop regardless of final claims. Validation
checks inventory, README, an accepted dependency manifest, application source,
tests or a test directory, and byte-nonempty required files. Readmes/manifests
default to root-level names. Source/test classification is a documented filename
heuristic, configurable through `ValidationPolicy`; it does not prove the files
are executable or semantically correct. Empty package initializers are excluded
from source/test candidates. All recognized source/test files and present
README/manifest candidates must be nonempty. An empty test directory produces
a warning rather than failing the assignment's directory-presence check.

Common build/dependency/cache directories and linked entries do not supply
validation artifacts. An inventory error or entry-limit overflow fails validation
instead of passing a partial scan. Required paths still use Workspace. Docker
is optional; no stack choice is inferred from the supplied architecture.

Optional caller-supplied `CommandResult` objects add deterministic exit/timeout
checks. Missing command evidence produces a warning. A finish-tool tests_run
claim is never treated as command evidence. The caller should supply final
verification runs after repairs; the validator evaluates every result supplied,
without choosing which earlier failure to disregard. It does not authenticate
results or execute more commands automatically.

`GenerationReport` composes the existing execution and validation dataclasses.
Its success requires a final response and passing configured checks. Turn-limit
exhaustion remains incomplete even if files pass validation. Provider SDK types
are absent from all these modules; the loop still depends on LLMProvider.

One synchronous loop is enough to demonstrate the mechanism. Multi-agent
coordination and agent frameworks would add lifecycle and dependency complexity
without helping this stage. No async pipeline, plugin discovery, service layer,
queue, database, or container system is required.

## Provider translation boundaries

The dependency direction remains AgentLoop -> LLMProvider. GeminiProvider alone
imports Google SDK classes; OpenAIProvider alone imports OpenAI SDK classes. The
factory selects mock, gemini, or openai without plugin
discovery. The SDK is optional. Its client is initialized with an explicit key,
a 120-second HTTP timeout, and one attempt (SDK retries disabled). Unknown providers,
missing keys, and unavailable adapters fail clearly without exposing configuration.

The adapter maps system text to system_instruction, user text to user content,
and assistant calls to model content. Neutral JSON schemas become function
declarations through parameters_json_schema. Automatic function calling is
explicitly disabled; no Python callable is passed to the SDK. Only AgentLoop
dispatches tools. Multiple calls return in order, followed by grouped function
responses containing success/error observations. Full stdout/stderr metadata is
not repeated when the observation already contains it.

Provider call IDs are preserved. Calls lacking IDs receive local UUIDs; the
adapter remembers that their wire IDs were absent. The adapter also caches exact
ordered response parts as plain serialized data indexed by call IDs, so opaque
continuation signatures survive the next request. This cache never enters neutral
models or artifacts. It is session-local: persistent resumption with a new adapter
instance is outside scope. Public responses contain only our dataclasses and JSON
values. Thought-marked text is excluded from public responses and thought summaries
are disabled in the request.

Authentication, quota, network, request, and malformed-response failures become
ProviderError with controlled messages and safe status/category/retryability
metadata. Raw SDK exceptions can contain request
data and are never forwarded. Blocked/truncated responses fail before tool dispatch;
an empty response is not interpreted as success. Tests use actual SDK value types
with a fake client, including signature round trips, without live requests.

Implementation references reviewed for this adapter:

- [Google Gen AI SDK documentation](https://googleapis.github.io/python-genai/)
  documents manual declarations, disabling automatic function calling, and SDK types.
- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)
  supplies the request/call/result protocol context.
- [Google model catalog](https://ai.google.dev/gemini-api/docs/models)
  lists gemini-3.8-flash, retained as the requested default. A model catalog
  entry does not establish account access or service health.

OpenAIProvider uses the Responses API with non-strict function declarations to
match the tools' optional arguments. It replays provider output items privately,
including encrypted reasoning continuation when present, and sends correlated
`function_call_output` observations after AgentLoop dispatches the tool. Requests
are stateless (`store=false`), with SDK retries disabled and a 120-second timeout.
Only public text and neutral tool calls leave the adapter. The protocol follows
the [official OpenAI function calling guide](https://developers.openai.com/api/docs/guides/function-calling).

The earlier Claude Code references motivate the iterative inspect/action/verify
mechanism. The explicit tool registry, filesystem/command separation, provider
boundary, and turn bound are this project's small implementation choices; they
are not claims of copied proprietary internals. No referenced source was copied.

## Generation composition and observable evidence

generation.py normalizes inputs, creates a dedicated Workspace, builds tools and
provider, constructs context, runs the loop, validates, and persists GenerationReport.
The prompt includes all normalized sections and UML payloads once, with topic fields
reduced to section IDs and sources reduced to filename/hash provenance. It retains
source assumptions separately from decisions and warns against silently rewriting
awkward requirements. Whole-source duplication remains in the archival JSON export,
not in the model context. It asks for a concise plan, not private reasoning.

Output is restricted to a project directory under the current project's generated/
root. The root itself, nonempty destinations, and linked path components are refused.
No cleanup/force option is provided. The host reserves .codeagent from filesystem
tools, excludes it from validation, and creates artifact files exclusively.
Subprocesses still have host permissions; artifact signing or tamper resistance
against arbitrary commands is not claimed.

The loop gained only an optional message observer, independent of providers or
persistence. Orchestration uses it to capture partial runs and write JSONL events.
Events include turn, tool name/ID, path, write/edit lengths, executable name, argument
count, and status. They omit assistant prose, file contents, command arguments,
stdout/stderr bodies, environment values, and private signatures. Reports include
bounded completion summaries and validation. The configured key is recursively
redacted from persisted strings. Runtime errors use generic messages; API errors
use the controlled adapter messages. A damaged/unwritable output can prevent saving.

The model marks real final test/build commands with verification=true. Orchestration
invalidates evidence after every write/edit attempt or ordinary command because those
may mutate files, even on failure. It retains the latest result per identical final
verification argument list. All retained checks must pass and at least one must exist.
This permits failed-test/repair/rerun workflows without treating intermediate failure
as permanent failure. It cannot determine whether a chosen command is a meaningful
test, nor detect all mutations performed inside a marked verification command.
These are explicit limits of structural and exit-status validation.

If a final documentation write invalidates the agent's last command evidence,
`code-agent verify` can rerun an explicit test/build command against the final
repository. It stores the initial outcome separately in the report, marks the
new evidence as independent post-run verification, and appends a distinct trace
event. It neither resumes the model nor attributes the later command to the
AgentLoop. The resulting success still requires a completed agent turn and all
deterministic checks to pass.

Generated subprocesses disable Python bytecode writes to avoid timestamp-cache reuse
after rapid same-size repairs. Other language build-cache semantics remain the generated
project's responsibility. The core validator remains usable independently with optional
command evidence; the generation service applies the stricter evidence requirement.

Provider/model configuration comes from CLI overrides, then process environment, then
current-directory dotenv values. Dotenv interpolation is disabled and os.environ is
not changed. Keys are excluded from config repr. Generation removes credential-like
environment entries before running commands and keeps the key out of prompts. No
security claim is made for arbitrary commands reading secrets elsewhere on the host.

## Remaining limitations

The full pipeline is tested offline, including write/read/test/repair/finish and failure
outcomes. The handoff's small Gemini tool loop succeeded, but the first full
attempt failed. On this machine, a full request and a one-line request both
returned HTTP 503 before any agent turn. The report now records safe error
metadata without exposing the SDK body. OpenAI's live tool-call round trip passed.
The OpenAI agent then produced a runnable Space Fractions repository with three
services and five passing integration tests. Its initial structural validation
failed after a final README write invalidated earlier test evidence. The explicit
`verify` command reran those tests against final files, preserved the initial
result, and recorded independent post-run validation as successful. Review found
scoring replay and answer-key exposure, which focused AgentLoop runs repaired.
The agent added two regression tests; seven tests now pass repeatedly. One
follow-up model request failed with a service error after the code changes, so
independent post-run verification supplies the final evidence. The resulting
application documents in-memory persistence and placeholder authentication as
demonstration limits; it has no student-facing browser UI and is not production
ready. Normalized JSON import,
resume/checkpoint support, context
compaction, token budgets, and OS process isolation remain deferred. Turn limits and
HTTP/command timeouts do not bound total token spending or the number of calls in one
response. Prompt separation is not a complete defense against malicious source text.
