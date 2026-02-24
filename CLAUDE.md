# TheHook — Project Memory

This project uses TheHook for persistent session memory. Knowledge extracted from sessions is stored in `.thehook/sessions/` and indexed in ChromaDB for retrieval.

## /save

When the user says `/save`, extract knowledge from the current conversation and save it:

1. Review the conversation and extract:
   - **Summary**: What was accomplished
   - **Conventions**: Coding patterns, naming standards, structural rules established
   - **Decisions**: Architecture choices, technology selections, and reasoning
   - **Gotchas**: Non-obvious pitfalls, edge cases, or bugs discovered

2. Pipe the extracted markdown to `thehook save`:

```bash
cat << 'EOF' | thehook save
## Summary
<what was accomplished>

## Conventions
<patterns and rules established>

## Decisions
<choices made and why>

## Gotchas
<pitfalls and edge cases discovered>
EOF
```

3. Confirm to the user what was saved.

Only include sections that have meaningful content. Skip empty sections.

## Session Start

At the beginning of a session, if `.thehook/` exists in the project, run:

```bash
thehook recall "project conventions decisions architecture"
```

Use the output as context to stay consistent with established patterns.
