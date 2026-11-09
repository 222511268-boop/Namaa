"""Consistent database/media backup and recovery to a NEW Compose project.

python scripts/recovery.py backup --project namaa --directory backups/daily
python scripts/recovery.py restore --project namaa-recovered --directory backups/daily --confirm-target namaa-recovered

Uses Docker's service environment; never prints database credentials. Backups contain account hashes and field
records: keep the destination private. Restore refuses the source project and a non-empty application database.
"""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compose(project, *args, **kwargs):
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            project,
            "--env-file",
            str(ROOT / ".env"),
            "-f",
            str(ROOT / "docker-compose.yml"),
            *args,
        ],
        cwd=ROOT,
        check=True,
        **kwargs,
    )


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def counts(project):
    tables = (
        "users",
        "sites",
        "observations",
        "site_baselines",
        "signals",
        "signal_decisions",
        "tasks",
        "task_findings",
        "finding_photos",
        "weather_daily",
        "irrigation_schedules",
        "plant_factors",
        "lst_observations",
        "lst_layers",
        "ai_briefs",
        "audit_events",
        "processing_runs",
    )
    sql = "SELECT json_build_object(" + ",".join(f"'{table}',(SELECT count(*) FROM {table})" for table in tables) + ")"
    result = compose(
        project,
        "exec",
        "-T",
        "db",
        "sh",
        "-c",
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"',
        "sh",
        sql,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout.strip())


def media_index(project):
    code = (
        "import hashlib,json; from pathlib import Path; root=Path('/data/media'); "
        "print(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() "
        "for p in root.rglob('*') if p.is_file()},sort_keys=True))"
    )
    result = compose(
        project, "run", "--rm", "--no-deps", "-T", "backend", "python", "-c", code, capture_output=True, text=True
    )
    return json.loads(result.stdout.strip())


def backup(project, directory):
    directory.mkdir(parents=True, exist_ok=False)
    running = compose(project, "ps", "--services", "--status", "running", capture_output=True, text=True).stdout.split()
    paused = [s for s in ("frontend", "worker", "backend") if s in running]
    try:
        if paused:
            compose(project, "stop", *paused)
        expected = counts(project)
        with (directory / "database.dump").open("wb") as output:
            compose(
                project,
                "exec",
                "-T",
                "db",
                "sh",
                "-c",
                'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc',
                stdout=output,
            )
        with (directory / "media.tar.gz").open("wb") as output:
            compose(
                project,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "backend",
                "tar",
                "-czf",
                "-",
                "-C",
                "/data/media",
                ".",
                stdout=output,
            )
        manifest = {
            "format": 1,
            "source_project": project,
            "created_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 -- host supports Python 3.10
            "counts": expected,
            "media": media_index(project),
            "sha256": {n: digest(directory / n) for n in ("database.dump", "media.tar.gz")},
        }
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Backup complete: {directory}")
    finally:
        if paused:
            compose(project, "start", *paused)


def restore(project, directory, confirmation):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or confirmation != project or project == manifest["source_project"]:
        raise SystemExit("Restore requires a new target project and --confirm-target matching it exactly.")
    if set(manifest["sha256"]) != {"database.dump", "media.tar.gz"}:
        raise SystemExit("Backup manifest is incomplete.")
    for name, expected in manifest["sha256"].items():
        if name not in ("database.dump", "media.tar.gz") or digest(directory / name) != expected:
            raise SystemExit("Backup checksum verification failed.")
    compose(project, "up", "-d", "--wait", "db")
    running = compose(project, "ps", "--services", "--status", "running", capture_output=True, text=True).stdout.split()
    if set(running) - {"db"}:
        raise SystemExit("Stop target application services before restoring.")
    query = "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename <> 'spatial_ref_sys'"
    result = compose(
        project,
        "exec",
        "-T",
        "db",
        "sh",
        "-c",
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"',
        "sh",
        query,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != "0":
        raise SystemExit("Target application database is not empty; restore refused.")
    compose(project, "build", "backend")
    # Refuse to merge an archive into pre-existing media.
    compose(
        project,
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "backend",
        "python",
        "-c",
        "from pathlib import Path; assert not any(Path('/data/media').iterdir()), 'Target media is not empty'",
    )
    with (directory / "database.dump").open("rb") as source:
        compose(
            project,
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error',
            stdin=source,
        )
    with (directory / "media.tar.gz").open("rb") as source:
        compose(
            project, "run", "--rm", "--no-deps", "-T", "backend", "tar", "-xzf", "-", "-C", "/data/media", stdin=source
        )
    actual = counts(project)
    if actual != manifest["counts"]:
        raise SystemExit(f"Restored record counts differ: {actual}")
    if media_index(project) != manifest["media"]:
        raise SystemExit("Restored media contents do not match the backup.")
    print(
        f"Restore verified in {project}: archive checksums, record counts and every media file's SHA-256 match. "
        "Application services remain stopped."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--confirm-target")
    args = parser.parse_args()
    if args.operation == "backup":
        backup(args.project, args.directory)
    else:
        restore(args.project, args.directory, args.confirm_target)
