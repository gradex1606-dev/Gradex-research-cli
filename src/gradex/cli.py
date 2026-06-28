"""Typer CLI application — all subcommands for `gradex`."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console

from gradex import __version__

app = typer.Typer(
    name="gradex",
    help="gradex: manage and interact with coding host plugins.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

console = Console()
_shutdown_event: asyncio.Event | None = None
_active_backend: Any = None


def _setup_shutdown_handler() -> None:
    """Register SIGINT handler for graceful cleanup."""

    def handler(signum: int, frame: Any) -> None:
        _ = signum, frame
        console.print("\n[yellow]Interrupted — cleaning up worktrees...[/yellow]")
        if _active_backend is not None:
            _active_backend._cleanup_all_sync()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handler)


def _parse_version_parts(version: str) -> tuple[int, ...]:
    """Parse dotted numeric version parts for simple ordering."""
    parts: list[int] = []
    for segment in version.split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _is_newer_version(latest: str, current: str) -> bool:
    """Return True when latest is newer than current."""
    latest_parts = _parse_version_parts(latest)
    current_parts = _parse_version_parts(current)
    width = max(len(latest_parts), len(current_parts))
    latest_norm = latest_parts + (0,) * (width - len(latest_parts))
    current_norm = current_parts + (0,) * (width - len(current_parts))
    return latest_norm > current_norm


def _version_callback(value: bool) -> None:
    """Print version string and exit when --version is supplied."""
    if value:
        console.print(f"gradex version [bold]{__version__}[/bold]")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """gradex entry point."""


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


@app.command()
def install(
    host: str = typer.Argument(
        ...,
        help="Coding host to install the plugin into (e.g. claude-code, cursor).",
    ),
    no_setup: bool = typer.Option(
        False,
        "--no-setup",
        "--skip-setup",
        help="Skip interactive model setup after install.",
    ),
) -> None:
    """Install the gradex plugin into the given coding host."""
    from gradex.config import is_llm_configured
    from gradex.hosts import get_installer
    from gradex.setup_wizard import run_model_setup

    try:
        installer = get_installer(host)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(
        f"[bold]Installing gradex plugin for {installer.display_name}...[/bold]"
    )
    result = installer.install()

    if result.success:
        console.print(f"[green]✓[/green] Installed to {result.plugin_dir}")
        for f in result.files_written:
            console.print(f"  [dim]wrote {f}[/dim]")
        if result.message:
            console.print(result.message)

        if not no_setup and not is_llm_configured():
            saved = run_model_setup(console, allow_skip=True)
            if saved is not None:
                _print_workflow_next_steps()
    else:
        console.print(f"[red]✗[/red] {result.message or 'Installation failed.'}")
        raise typer.Exit(code=1)


def _print_workflow_next_steps() -> None:
    console.print()
    console.print("Next: [bold]gradex discover \"make this repo faster\"[/bold]")
    console.print("      [bold]gradex optimize[/bold]")


# ---------------------------------------------------------------------------
# configure / models
# ---------------------------------------------------------------------------


@app.command()
def configure() -> None:
    """Set up or update your LLM provider, model, and API key."""
    from gradex.config import is_llm_configured
    from gradex.setup_wizard import run_model_setup

    saved = run_model_setup(
        console,
        allow_skip=False,
        confirm_overwrite=is_llm_configured(),
    )
    if saved is not None:
        _print_workflow_next_steps()


@app.command()
def models(
    provider: str = typer.Option(
        "",
        help="Provider to list models for (default: from saved config or groq).",
    ),
) -> None:
    """List recommended models for a provider."""
    from gradex.config import load_llm_config
    from gradex.setup_wizard import print_models

    chosen = provider.strip() or load_llm_config().provider
    try:
        print_models(console, chosen)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@app.command()
def doctor(
    host: str = typer.Argument(
        ...,
        help="Coding host to check the environment for (e.g. claude-code, cursor).",
    ),
) -> None:
    """Check the environment required by the given coding host."""
    from gradex.hosts import get_installer

    try:
        installer = get_installer(host)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"[bold]Checking {host} ({installer.display_name})...[/bold]\n")
    issues = installer.doctor()

    if not issues:
        console.print("[bold green]All checks passed.[/bold green]")
        return

    errors = [i for i in issues if i.severity == "error"]
    for issue in issues:
        color = "red" if issue.severity == "error" else "yellow"
        badge = issue.severity.upper()
        console.print(f"[{color}]{badge}[/{color}] {issue.message}")
        console.print(f"  [dim]Fix: {issue.fix}[/dim]")

    console.print()
    if errors:
        console.print("[bold red]Some checks failed.[/bold red]")
        raise typer.Exit(code=1)
    else:
        console.print("[yellow]Warnings found — not blocking.[/yellow]")


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------


@app.command()
def dashboard(
    port: int = typer.Option(0, help="Port to listen on (0 = auto-select)."),
    no_browser: bool = typer.Option(
        False, help="Skip opening the browser automatically."
    ),
) -> None:
    """Start the live gradex dashboard."""
    import threading
    import webbrowser

    import uvicorn

    from gradex.dashboard.server import create_app, find_free_port

    actual_port = port if port != 0 else find_free_port()
    url = f"http://127.0.0.1:{actual_port}"

    console.print(f"[bold green]Dashboard live:[/bold green] {url}")

    if not no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    uvicorn.run(create_app(), host="127.0.0.1", port=actual_port, log_level="warning")


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


@app.command()
def upgrade() -> None:
    """Check for new Gradex releases on PyPI."""

    async def _check() -> str | None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://pypi.org/pypi/gradex/json")
            resp.raise_for_status()
            payload = resp.json()
            info = payload.get("info")
            if not isinstance(info, dict):
                return None
            version = info.get("version")
            if not isinstance(version, str):
                return None
            return version

    try:
        latest = asyncio.run(_check())
    except Exception:  # noqa: BLE001
        console.print("[yellow]Could not check for updates.[/yellow]")
        return

    if latest is None:
        console.print("[yellow]Could not check for updates.[/yellow]")
        return

    if _is_newer_version(latest, __version__):
        console.print(
            f"[green]New version available: {latest}[/green]\n"
            "Run: pip install --upgrade gradex"
        )
    else:
        console.print(f"[green]gradex {__version__} is up to date.[/green]")


# ---------------------------------------------------------------------------
# run-experiment  (hidden — for manual testing only)
# ---------------------------------------------------------------------------


@app.command("run-experiment", hidden=True)
def run_experiment(
    benchmark: str = typer.Option(..., help="Benchmark command (quoted)."),
    gate: list[str] = typer.Option([], help="Gate command (repeat for multiple)."),  # noqa: B008
    direction: str = typer.Option("lower", help="Metric direction: higher or lower."),
    experiment_id: str = typer.Option(
        "", help="Experiment ID (auto-generated if empty)."
    ),
) -> None:
    """Run a single experiment in a new worktree.  For manual testing."""
    import shlex
    import uuid

    from gradex.backends.worktree import WorktreeBackend
    from gradex.runner.benchmark import BenchmarkRunner
    from gradex.runner.gate import GateRunner

    global _active_backend, _shutdown_event
    _setup_shutdown_handler()
    _shutdown_event = asyncio.Event()

    eid = experiment_id or str(uuid.uuid4())
    backend = WorktreeBackend()
    _active_backend = backend
    console.print(
        f"[bold]Direction:[/bold] {direction}  [bold]Experiment:[/bold] {eid}"
    )

    async def _run() -> None:
        workspace = await backend.create_workspace(eid)
        console.print(f"[bold]Workspace:[/bold] {workspace}")
        try:
            bench_result = await BenchmarkRunner(backend).run(
                workspace, shlex.split(benchmark)
            )
            console.print(
                f"[bold]Score:[/bold] {bench_result.score}"
                f"  (parse_error: {bench_result.parse_error})"
            )
            gate_result = await GateRunner(backend).run(workspace, list(gate))
            status = (
                "[bold green]PASSED[/bold green]"
                if gate_result.passed
                else "[bold red]FAILED[/bold red]"
            )
            console.print(f"[bold]Gate:[/bold] {status}")
            for failure in gate_result.failures:
                console.print(f"  [red]X[/red] {failure}")
        finally:
            await backend.cleanup_workspace(workspace)
            console.print("[dim]Workspace cleaned.[/dim]")

    try:
        asyncio.run(_run())
    finally:
        _active_backend = None


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


@app.command()
def discover(
    hint: str = typer.Argument(
        "", help="What to optimise, e.g. 'make the parser faster'."
    ),
    provider: str = typer.Option(
        "",
        help="LLM provider: groq, openrouter, anthropic, openai, ollama.",
    ),
    model: str = typer.Option("", help="Model name override."),
    api_key: str = typer.Option("", help="API key (or set in ~/.gradex/config.toml)."),
) -> None:
    """Discover what to optimise in this repo and capture a baseline score."""
    import asyncio

    from gradex.ai.client import LLMClient
    from gradex.ai.discover import DiscoverSkill
    from gradex.backends.worktree import WorktreeBackend
    from gradex.config import is_llm_configured, load_llm_config
    config = load_llm_config()
    if provider:
        config.provider = provider
    if model:
        config.model = model
    if api_key:
        config.api_key = api_key

    if not is_llm_configured() and not provider and not api_key:
        console.print(
            "[dim]Tip: run [bold]gradex configure[/bold] to save your provider "
            "and API key.[/dim]"
        )

    console.print(
        f"[bold]Provider:[/bold] {config.provider} / {config.effective_model()}"
    )
    if config.provider == "groq":
        console.print(
            "[dim]Free tier: 14,400 req/day. Get key at console.groq.com[/dim]"
        )
    elif config.provider == "ollama":
        console.print(
            "[dim]Local model — make sure Ollama is running (ollama serve)[/dim]"
        )
    elif config.provider == "openrouter":
        console.print(
            "[dim]Free-tier models for testing. Get key at openrouter.ai/keys[/dim]"
        )
        console.print(
            "[dim]For serious optimize runs, prefer --provider groq or a paid model[/dim]"
        )

    client = LLMClient(config)
    backend = WorktreeBackend()
    skill = DiscoverSkill(client=client, backend=backend)

    async def _run() -> None:
        try:
            with console.status("Scanning repository..."):
                result = await skill.run(Path.cwd(), hint=hint)
        except ValueError as exc:
            console.print(f"[red]Discover failed:[/red] {exc}")
            raise typer.Exit(code=1) from None
        console.print(f"[green]✓[/green] Target:   {result.optimization_target}")
        console.print(f"[green]✓[/green] Language: {result.primary_language}")
        console.print(f"[green]✓[/green] Metric:   {result.metric}")
        console.print(f"[green]✓[/green] Baseline: {result.baseline_score}")
        console.print(f"[green]✓[/green] Gate:     {result.gate_cmds}")
        console.print(f"[green]✓[/green] Run ID:   {result.run_id[:8]}")
        console.print()
        console.print("Dashboard: run [bold]gradex dashboard[/bold] to monitor")
        console.print("Next:       run [bold]gradex optimize[/bold] to start improving")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# optimize
# ---------------------------------------------------------------------------


@app.command()
def optimize(
    subagents: int = typer.Option(3, help="Parallel subagents per round"),
    budget: int = typer.Option(5, help="Max experiments per subagent"),
    stall: int = typer.Option(3, help="Rounds without improvement before stopping"),
    provider: str = typer.Option(
        "",
        help="LLM provider: groq, openrouter, anthropic, openai, ollama.",
    ),
    model: str = typer.Option("", help="Model override"),
    api_key: str = typer.Option("", help="API key"),
    run_id: str = typer.Option("", help="Run ID to continue (default: latest run)"),
) -> None:
    """Run the optimization loop on the current repo."""
    from gradex.ai.brief import BriefGenerator
    from gradex.ai.client import LLMClient
    from gradex.backends.worktree import WorktreeBackend
    from gradex.config import load_llm_config
    from gradex.dashboard.broadcaster import DashboardBroadcaster
    from gradex.orchestrator import Orchestrator, OrchestratorConfig
    from gradex.repository import RunRepository
    from gradex.runner.benchmark import BenchmarkRunner
    from gradex.runner.gate import GateRunner
    from gradex.subagent import SubagentRunner

    global _active_backend, _shutdown_event
    _setup_shutdown_handler()
    _shutdown_event = asyncio.Event()

    cfg = load_llm_config()
    if provider:
        cfg.provider = provider
    if model:
        cfg.model = model
    if api_key:
        cfg.api_key = api_key

    run_repo = RunRepository()
    run = run_repo.get(run_id) if run_id else run_repo.get_latest()
    if run is None:
        console.print("[red]No run found. Run `gradex discover` first.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Run:[/bold] {run.id[:8]}")
    console.print(f"[bold]Benchmark:[/bold] {run.benchmark_cmd}")
    console.print(f"[bold]Baseline:[/bold] {run.baseline_score}")
    console.print(f"[bold]Provider:[/bold] {cfg.provider} / {cfg.effective_model()}")
    console.print(
        f"[bold]Subagents:[/bold] {subagents} | Budget: {budget} | Stall: {stall}"
    )
    console.print()

    backend = WorktreeBackend()
    _active_backend = backend
    llm_client = LLMClient(cfg)
    bench_runner = BenchmarkRunner(backend)
    gate_runner = GateRunner(backend)
    brief_gen = BriefGenerator(llm_client)
    broadcaster = DashboardBroadcaster.get()
    subagent_runner = SubagentRunner(
        backend=backend,
        benchmark_runner=bench_runner,
        gate_runner=gate_runner,
        llm_client=llm_client,
        run=run,
    )
    orch_config = OrchestratorConfig(
        subagents=subagents,
        budget=budget,
        stall=stall,
    )
    orchestrator = Orchestrator(
        run=run,
        subagent_runner=subagent_runner,
        brief_generator=brief_gen,
        broadcaster=broadcaster,
        config=orch_config,
    )

    async def _run() -> None:
        with console.status("Running optimization loop... (open dashboard to monitor)"):
            result = await orchestrator.run()
        console.print("\n[bold green]Done.[/bold green]")
        console.print(f"Rounds:       {result.rounds_completed}")
        console.print(f"Experiments:  {result.total_experiments}")
        console.print(f"Passed:       {result.experiments_passed}")
        console.print(f"Baseline:     {result.baseline_score}")
        if result.best_score is not None:
            console.print(f"Best:         {result.best_score}")
            if result.improvement_pct is not None:
                console.print(f"Improvement:  {result.improvement_pct:.1f}%")
        console.print(f"Stopped:      {result.stopped_reason}")

    try:
        asyncio.run(_run())
    finally:
        _active_backend = None


# ---------------------------------------------------------------------------
# traces
# ---------------------------------------------------------------------------


@app.command()
def traces(
    experiment: str = typer.Option(
        "",
        "--experiment",
        "-e",
        help="Experiment ID or 8-char prefix (default: latest on latest run).",
    ),
    run_id: str = typer.Option("", help="Run ID to search within."),
    tail: int = typer.Option(0, help="Show only the last N entries."),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON."),
) -> None:
    """Show trace timeline for an experiment."""
    import json
    from datetime import datetime

    from gradex.repository import ExperimentRepository, RunRepository
    from gradex.traces import TraceReader, trace_path_for

    exp_repo = ExperimentRepository()
    run_repo = RunRepository()

    resolved_id: str | None = None
    if experiment:
        resolved_id = exp_repo.resolve_id(experiment, run_id or None)
    else:
        run = run_repo.get(run_id) if run_id else run_repo.get_latest()
        if run is not None:
            exps = exp_repo.list_by_run(run.id)
            if exps:
                resolved_id = exps[-1].id

    if resolved_id is None:
        console.print("[red]No experiment found.[/red]")
        raise typer.Exit(1)

    entries = TraceReader(trace_path_for(resolved_id)).read_all()
    if tail > 0:
        entries = entries[-tail:]

    if as_json:
        console.print(json.dumps({"experiment_id": resolved_id, "entries": entries}, indent=2))
        return

    console.print(f"[bold]Experiment[/bold] {resolved_id[:8]}  [dim]({resolved_id})[/dim]")
    if not entries:
        console.print("[dim]No trace entries.[/dim]")
        return

    for entry in entries:
        ts = entry.get("ts", 0)
        ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "??:??:??"
        level = entry.get("level", "info")
        msg = entry.get("msg", "")
        data = entry.get("data", {})
        line = f"[dim]{ts_str}[/dim] [{level}] {msg}"
        console.print(line)
        if data:
            console.print(f"  [dim]{json.dumps(data)}[/dim]")


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


@app.command()
def stats(
    run_id: str = typer.Option("", help="Run ID (default: latest)"),
    export_json: str = typer.Option("", "--json", help="Export to JSON file"),
    export_csv: str = typer.Option("", "--csv", help="Export to CSV file"),
) -> None:
    """Show detailed analytics for a run."""
    from gradex.analytics import RunAnalytics
    from gradex.export import RunExporter
    from gradex.repository import RunRepository

    run_repo = RunRepository()
    run = run_repo.get(run_id) if run_id else run_repo.get_latest()
    if run is None:
        console.print("[red]No run found. Run `gradex discover` first.[/red]")
        raise typer.Exit(1)

    analytics = RunAnalytics()
    summary = analytics.get_run_summary(run.id)
    score_points = analytics.get_score_over_time(run.id)

    console.print()
    console.print(
        f"[bold]Run:[/bold] {summary.run_id_short}  "
        f"[dim]{summary.created_at.strftime('%Y-%m-%d %H:%M')}[/dim]"
    )
    console.print(f"[bold]Benchmark:[/bold] {summary.benchmark_cmd}")
    console.print(f"[bold]Metric:[/bold] {summary.metric_direction}")
    console.print()

    baseline_str = f"{summary.baseline_score:.4f}"
    best_str = f"{summary.best_score:.4f}" if summary.best_score is not None else "—"

    if summary.improvement_pct is not None and summary.improvement_pct > 0:
        improvement_str = f"[green]+{summary.improvement_pct:.1f}%[/green]"
    elif summary.improvement_pct is not None:
        improvement_str = f"[red]{summary.improvement_pct:.1f}%[/red]"
    else:
        improvement_str = "—"

    console.print(f"  Baseline score:   {baseline_str}")
    console.print(f"  Best score:       {best_str}")
    console.print(f"  Improvement:      {improvement_str}")
    console.print()

    b = summary.breakdown
    console.print(f"  Experiments:      {b.total} total")
    console.print(f"    [green]Passed:[/green]    {b.passed}")
    console.print(f"    [red]Rejected:[/red]  {b.rejected}  (gate failed)")
    console.print(f"    [dim]Failed:[/dim]    {b.failed}   (crash/timeout)")
    console.print(f"    Pass rate:       {b.pass_rate}%")
    console.print()
    console.print(f"  Duration:         {summary.duration_seconds:.0f}s")
    console.print(f"  Gate commands:    {', '.join(summary.gate_cmds) or 'none'}")
    if summary.llm_call_count > 0 or summary.total_input_tokens > 0:
        console.print()
        console.print(
            f"  LLM usage:        {summary.llm_call_count} calls · "
            f"{summary.total_input_tokens:,} in / {summary.total_output_tokens:,} out tokens"
        )
        console.print(
            f"  Est. cost:        ${summary.estimated_cost_usd:.4f} "
            f"[dim]({summary.cost_model_label})[/dim]"
        )

    if score_points:
        console.print()
        console.print("[bold]Score progression (passed experiments):[/bold]")
        for i, pt in enumerate(score_points):
            delta_str = ""
            if pt.delta_from_previous is not None:
                sign = "↓" if summary.metric_direction == "lower" else "↑"
                delta_str = f"  {sign} {abs(pt.delta_from_previous):.4f}"
            console.print(
                f"  [{i + 1}] {pt.experiment_id_short}  score={pt.score:.4f}{delta_str}"
            )

    if export_json:
        exporter = RunExporter(analytics)
        path = exporter.to_json(run.id, Path(export_json))
        console.print(f"\n[green]✓[/green] Exported JSON: {path}")

    if export_csv:
        exporter = RunExporter(analytics)
        path = exporter.to_csv(run.id, Path(export_csv))
        console.print(f"[green]✓[/green] Exported CSV: {path}")


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@app.command()
def report(
    run_id: str = typer.Option("", help="Run ID (default: latest)"),
    output: str = typer.Option(
        "gradex-report.html",
        "--output",
        "-o",
        help="Output HTML file path",
    ),
) -> None:
    """Export a shareable HTML report for a run."""
    from gradex.export import RunExporter
    from gradex.repository import RunRepository

    run_repo = RunRepository()
    run = run_repo.get(run_id) if run_id else run_repo.get_latest()
    if run is None:
        console.print("[red]No run found. Run `gradex discover` first.[/red]")
        raise typer.Exit(1)

    exporter = RunExporter()
    path = exporter.to_html(run.id, Path(output))
    console.print(f"[green]✓[/green] Report saved: {path}")
    console.print("[dim]Share this file or open it in any browser.[/dim]")


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


@app.command()
def history(
    limit: int = typer.Option(10, help="Number of runs to show"),
) -> None:
    """List recent optimization runs."""
    from gradex.analytics import RunAnalytics

    analytics = RunAnalytics()
    runs = analytics.get_all_runs(limit=limit)

    if not runs:
        console.print("[dim]No runs found. Run `gradex discover` first.[/dim]")
        raise typer.Exit(0)

    console.print()
    console.print(f"[bold]Recent runs[/bold] (showing {len(runs)}):")
    console.print()

    for r in runs:
        if r.improvement_pct is not None and r.improvement_pct > 0:
            status = f"[green]+{r.improvement_pct:.1f}%[/green]"
        elif r.breakdown.total == 0:
            status = "[dim]no experiments[/dim]"
        else:
            status = "[dim]no improvement[/dim]"

        date_str = r.created_at.strftime("%Y-%m-%d %H:%M")
        console.print(
            f"  {r.run_id_short}  {date_str}  "
            f"{r.breakdown.total:>3} experiments  {status}"
        )
        console.print(f"           [dim]{r.benchmark_cmd}[/dim]")
