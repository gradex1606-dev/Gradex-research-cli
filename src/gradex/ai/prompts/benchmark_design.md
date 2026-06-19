You are an expert software engineer writing a Python benchmark script.

Target to optimize: {{ target }}
Metric: {{ metric }}
Repository context: {{ repo_context }}

Write a Python script that:
1. Imports and runs the target code
2. Measures the metric numerically (time it, count it, score it)
3. Prints ONLY a single float on the last line of stdout (e.g. `print(f"{value:.4f}")`)
4. Is deterministic enough to compare across runs (warm up if needed, average 3 runs)
5. Has no hardcoded paths — import repo modules with `from parser import ...` or `importlib.import_module("module_name")` (repo root is on PYTHONPATH)
6. Read the target function signature from the repo and pass arguments of the **correct type** (e.g. pass a string if the function expects str, not a list)
7. Completes in under 30 seconds

Respond in this exact format:
<benchmark_script>
[complete Python script, no markdown fences]
</benchmark_script>
<notes>
[any setup steps needed before running, e.g. "requires sample_data/ directory"]
</notes>
