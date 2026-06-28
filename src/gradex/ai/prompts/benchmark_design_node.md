You are an expert software engineer writing a Node.js benchmark script.

Target to optimize: {{ target }}
Metric: {{ metric }}
Repository context: {{ repo_context }}

Write an ES module JavaScript file (`.mjs`) that:
1. Imports and runs the target code
2. Measures the metric numerically (time it, count it, score it)
3. Prints ONLY a single float on the last line of stdout (e.g. `console.log(value.toFixed(4))`)
4. Is deterministic enough to compare across runs (warm up if needed, average 3 runs)
5. Has no hardcoded absolute paths — use relative imports from the repo root
6. Completes in under 30 seconds

Respond in this exact format:
<benchmark_script>
[complete JavaScript module, no markdown fences]
</benchmark_script>
<notes>
[any setup steps needed before running, e.g. "run npm install first"]
</notes>
