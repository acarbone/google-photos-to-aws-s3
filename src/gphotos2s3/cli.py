"""gphotos2s3 CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

from gphotos2s3 import aws_credentials, report, wizard
from gphotos2s3.config import Config, config_path, db_path, lock_path
from gphotos2s3.pipeline import LockHeldError, ProcessLock, run_pipeline
from gphotos2s3.state import open_state
from gphotos2s3.uploader import verify_uploaded

console = Console()


def _resolve_zip_paths(sources: list[str]) -> list[Path]:
    paths: list[Path] = []
    for source in sources:
        p = Path(source).expanduser()
        if p.is_dir():
            paths.extend(sorted(p.glob("*.zip")))
        elif p.is_file():
            paths.append(p)
    return paths


def _load_or_init_config(state_dir: Path, reconfigure: bool) -> Config:
    path = config_path(state_dir)
    if path.exists() and not reconfigure:
        return Config.load(path)
    config = wizard.run_wizard(state_dir)
    config.save(path)
    return config


def cmd_init(args: argparse.Namespace) -> int:
    state_dir: Path = args.state_dir
    config = wizard.run_wizard(state_dir)
    config.save(config_path(state_dir))
    console.print("[green]Setup complete.[/green] Run `gphotos2s3 run` to start the backup.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    state_dir: Path = args.state_dir
    config = _load_or_init_config(state_dir, args.reconfigure)
    if args.no_dedupe:
        config.dedupe = False
    if args.workers:
        config.workers = args.workers
    if args.max_attempts:
        config.max_attempts = args.max_attempts
    if args.source:
        config.sources = args.source
    if args.profile:
        config.aws_profile = args.profile

    lock = ProcessLock(lock_path(state_dir))
    try:
        lock.acquire()
    except LockHeldError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    try:
        zip_paths = _resolve_zip_paths(config.sources)
        if not zip_paths:
            console.print("[red]No Takeout .zip files found in the configured sources.[/red]")
            return 1

        s3_client = aws_credentials.build_s3_client(config.aws_profile, config.region)

        with (
            open_state(db_path(state_dir)) as state,
            Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeRemainingColumn(),
                console=console,
            ) as progress,
        ):
            task = progress.add_task("Uploading", total=None)

            def on_progress(_row: object) -> None:
                progress.update(task, advance=1)

            summary = run_pipeline(
                state,
                s3_client,
                config,
                zip_paths,
                threshold=5,
                on_progress=on_progress,
            )
        console.print(report.format_run_summary(summary))
        return 1 if summary.halted else 0
    finally:
        lock.release()


def cmd_status(args: argparse.Namespace) -> int:
    state_dir: Path = args.state_dir
    with open_state(db_path(state_dir)) as state:
        console.print(report.format_status(state))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    state_dir: Path = args.state_dir
    config = Config.load(config_path(state_dir))
    s3_client = aws_credentials.build_s3_client(config.aws_profile, config.region)
    with open_state(db_path(state_dir)) as state:
        rows = list(state.iter_by_status("uploaded"))
        mismatches = verify_uploaded(s3_client, config.bucket, rows)
        for row, reason in mismatches:
            state.mark_verify_failed(row.id, reason)
        console.print(report.format_verify_results(mismatches))
    return 0


def cmd_retry_failed(args: argparse.Namespace) -> int:
    state_dir: Path = args.state_dir
    config = Config.load(config_path(state_dir))
    with open_state(db_path(state_dir)) as state:
        n = state.reset_failed_for_retry(config.max_attempts)
        console.print(f"Reset {n} row(s) to pending.")
    return cmd_run(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gphotos2s3", description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Directory for local state/config (default: ~/.gphotos2s3)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Run the interactive setup wizard")
    p_init.set_defaults(func=cmd_init)

    p_run = sub.add_parser("run", help="Discovery + upload loop, resumable")
    p_run.add_argument("--reconfigure", action="store_true")
    p_run.add_argument("--source", action="append", default=None)
    p_run.add_argument("--no-dedupe", action="store_true")
    p_run.add_argument("--workers", type=int, default=None)
    p_run.add_argument("--max-attempts", type=int, default=None)
    p_run.add_argument("--profile", type=str, default=None)
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="Print progress summary")
    p_status.set_defaults(func=cmd_status)

    p_verify = sub.add_parser("verify", help="Re-check uploaded files' integrity")
    p_verify.set_defaults(func=cmd_verify)

    p_retry = sub.add_parser("retry-failed", help="Reset failed rows and run")
    p_retry.add_argument("--reconfigure", action="store_true")
    p_retry.add_argument("--source", action="append", default=None)
    p_retry.add_argument("--no-dedupe", action="store_true")
    p_retry.add_argument("--workers", type=int, default=None)
    p_retry.add_argument("--max-attempts", type=int, default=None)
    p_retry.add_argument("--profile", type=str, default=None)
    p_retry.set_defaults(func=cmd_retry_failed)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.state_dir is None:
        from gphotos2s3.config import DEFAULT_STATE_DIR

        args.state_dir = DEFAULT_STATE_DIR
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
