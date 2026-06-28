You are an expert software engineer identifying regression tests for a Node.js/TypeScript optimization task.

Target to optimize: {{ target }}
Repository test files found: {{ test_files }}

Identify the test command(s) that must pass after every experiment.
Prefer commands that exist in package.json scripts when available.
Use ONLY paths from the "Repository test files found" list when referencing specific test files.
If package.json has a "test" script, you may use `npm test`.
Otherwise prefer: `npx vitest run`, `npx jest`, or `node --test` with specific files.

Respond in this exact format:
<gate_cmds>
["npm test"]
</gate_cmds>
<rationale>
[why these tests are the right gate]
</rationale>
