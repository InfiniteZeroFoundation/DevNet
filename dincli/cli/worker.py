import hashlib
import json
import os
import subprocess
from importlib.resources import files
from pathlib import Path
from typing import Optional, Sequence

from dincli.cli.utils import WORKER_CACHE_DIR

WORKER_IMAGE = "din-worker:dev"


def _host_user_flag() -> list[str]:
    # Run as the host UID/GID so anything the container writes into bind
    # mounts (packages cache, output dirs) stays owned by the invoking user
    # instead of root, which would otherwise block later host-side writes.
    return ["--user", f"{os.getuid()}:{os.getgid()}"]


def ensure_worker_image(console) -> None:
    inspect_result = subprocess.run(
        ["docker", "image", "inspect", WORKER_IMAGE],
        text=True,
        capture_output=True,
        check=False,
    )
    if inspect_result.returncode == 0:
        return

    dincli_package_root = Path(str(files("dincli")))
    dockerfile_path = dincli_package_root / "docker" / "worker" / "Dockerfile"
    build_context = dincli_package_root.parent
    console.print(f"Docker image {WORKER_IMAGE} not found. Building it now...")
    build_result = subprocess.run(
        [
            "docker",
            "build",
            "-f",
            str(dockerfile_path),
            "-t",
            WORKER_IMAGE,
            str(build_context),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if build_result.stdout:
        console.print(build_result.stdout)
    if build_result.returncode != 0:
        if build_result.stderr:
            console.print(build_result.stderr)
        raise RuntimeError(f"Failed to build Docker image {WORKER_IMAGE}")


def get_worker_requirements_path(model_base_dir: Path, role: str) -> Path:
    return model_base_dir / "requirements" / role / "requirements.txt"


def get_worker_packages_dir(network: str, model_id: int) -> Path:
    # Shared across clients/auditors/aggregators for a given model: they're
    # expected to pin the same manifest requirements.txt, so one install
    # serves all roles instead of duplicating multi-GB dependencies per role.
    return WORKER_CACHE_DIR / network / f"model_{model_id}" / "worker-packages"


def ensure_worker_packages_installed(requirements_path: Path, packages_dir: Path, console) -> Optional[Path]:
    """Install whatever the model owner pinned in the manifest's requirements.txt.

    Installed once per requirements.txt content (tracked by hash) into
    WORKER_CACHE_DIR, kept separate from the dincli cache so the install
    container never touches manifest/service/wallet state.
    """
    if not requirements_path.exists():
        return None

    requirements_text = requirements_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(requirements_text.encode("utf-8")).hexdigest()
    marker_path = packages_dir / ".requirements.sha256"
    if marker_path.exists() and marker_path.read_text(encoding="utf-8").strip() == digest:
        console.print(f"[green]✓ Worker packages already installed at {packages_dir}[/green]")
        return packages_dir

    packages_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"Installing worker requirements from {requirements_path} into {packages_dir} ...")
    install_result = subprocess.run(
        [
            "docker", "run", "--rm",
            *_host_user_flag(),
            "-e", "HOME=/tmp",
            "--entrypoint", "pip",
            "-v", f"{requirements_path.resolve()}:/din/requirements.txt:ro",
            "-v", f"{packages_dir.resolve()}:/din/packages:rw",
            WORKER_IMAGE,
            "install", "--no-cache-dir", "--target", "/din/packages", "-r", "/din/requirements.txt",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if install_result.stdout:
        console.print(install_result.stdout)
    if install_result.returncode != 0:
        if install_result.stderr:
            console.print(install_result.stderr)
        raise RuntimeError("Failed to install worker requirements into the packages cache.")

    marker_path.write_text(digest, encoding="utf-8")
    console.print(f"[bold green]Worker packages ready at {packages_dir}[/bold green]")
    return packages_dir


def write_worker_job(jobs_dir: Path, job_name: str, job: dict) -> tuple[Path, Path]:
    jobs_dir.mkdir(parents=True, exist_ok=True)
    output_dir = jobs_dir / f"{job_name}_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    job_path = jobs_dir / f"{job_name}.json"
    job = dict(job)
    job.setdefault("output_path", "/din/output/result.json")
    job_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    return job_path, output_dir


def run_worker_container(
    container_name: str,
    model_base_dir: Path,
    job_path: Path,
    output_dir: Path,
    writable_subdirs: Sequence[Path] = (),
    packages_dir: Optional[Path] = None,
):
    """Run a worker job. The model directory is mounted read-only by default;
    only the specific subdirectories a role needs to write into (e.g. a
    client's own output dir) are bind-mounted read-write on top of it.
    """
    model_base_dir = model_base_dir.resolve()
    cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        *_host_user_flag(),
        "-e", "HOME=/tmp",
        "--cpus", "2",
        "--memory", "4g",
        "--network", "none",
        "-v", f"{model_base_dir}:/din/model:ro",
    ]
    for subdir in writable_subdirs:
        subdir = subdir.resolve()
        subdir.mkdir(parents=True, exist_ok=True)
        relative = subdir.relative_to(model_base_dir)
        cmd += ["-v", f"{subdir}:/din/model/{relative.as_posix()}:rw"]
    cmd += [
        "-v", f"{job_path.resolve()}:/din/job/job.json:ro",
        "-v", f"{output_dir.resolve()}:/din/output:rw",
    ]
    if packages_dir is not None:
        cmd += ["-v", f"{packages_dir.resolve()}:/din/packages:ro", "-e", "PYTHONPATH=/din/packages"]
    cmd.append(WORKER_IMAGE)
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def read_worker_result(output_dir: Path) -> dict:
    result_path = output_dir / "result.json"
    if not result_path.exists():
        raise FileNotFoundError(f"Worker did not write result file at {result_path}")
    return json.loads(result_path.read_text(encoding="utf-8"))
