# Architecture inputs

This directory contains the versioned source material used by CodeAgentArc's
checked-in Space Fractions example.

- `inputs/Architecture_Documentation.md` contains the written system design.
- `inputs/Architecture_View.md` contains the PlantUML architecture views.

Both files are runtime inputs, so they belong in the repository. The
`code-agent normalize` and `code-agent generate` commands use these paths by
default when run from the repository root.

Generated normalization exports and generated applications belong under
`generated/`; implementation code for parsing these inputs belongs under
`src/code_agent/architecture/`.
