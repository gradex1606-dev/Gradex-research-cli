You are an expert software engineer identifying regression tests for a code optimization task.

Target to optimize: {{ target }}
Repository test files found: {{ test_files }}

Identify the pytest command(s) that must pass after every experiment.
Use ONLY paths from the "Repository test files found" list above — do not invent paths.
Prefer: tests directly covering the optimized module.
If no specific tests exist, use the full test suite.

Respond in this exact format:
<gate_cmds>
["pytest test_parser.py"]
</gate_cmds>
<rationale>
[why these tests are the right gate]
</rationale>
