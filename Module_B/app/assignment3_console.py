from __future__ import annotations

import copy
import datetime
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path


MODULE_A_SCENARIOS = [
    "Atomicity",
    "Consistency",
    "Isolation",
    "Durability",
    "Recovery - Incomplete Transaction",
    "Recovery - Journal Replay",
]

MODULE_B_SCENARIOS = [
    "rollback_integrity",
    "delete_race",
    "mixed_load",
]

RUN_ALL_SCENARIOS = [
    "Module A",
    "Module B",
]

MODULE_A_HEADERS = {
    "[Atomicity]": "Atomicity",
    "[Consistency]": "Consistency",
    "[Isolation]": "Isolation",
    "[Durability]": "Durability",
    "[Recovery - Incomplete Transaction]": "Recovery - Incomplete Transaction",
    "[Recovery - Journal Replay]": "Recovery - Journal Replay",
}

MODULE_B_HEADERS = {
    "[Rollback Integrity]": "rollback_integrity",
    "[Delete Race]": "delete_race",
    "[Mixed Load]": "mixed_load",
}


class Assignment3Console:
    def __init__(self, repo_root: Path, module_b_dir: Path):
        self.repo_root = Path(repo_root)
        self.module_a_dir = self.repo_root / "Module_A"
        self.module_b_dir = Path(module_b_dir)
        self._lock = threading.Lock()
        self._jobs = {
            "module_a": self._new_job("module_a"),
            "module_b": self._new_job("module_b"),
            "run_all": self._new_job("run_all"),
        }

    def snapshot(self):
        with self._lock:
            return {name: self._public_job_state(job) for name, job in self._jobs.items()}

    def start_module_a(self, triggered_by_role: str):
        return self._start_single_job("module_a", triggered_by_role, self._run_module_a_job)

    def start_module_b(self, triggered_by_role: str):
        return self._start_single_job("module_b", triggered_by_role, self._run_module_b_job)

    def start_run_all(self, triggered_by_role: str):
        with self._lock:
            if self._jobs["run_all"]["status"] == "running":
                snapshot = self._snapshot_locked()
                return False, "Run All is already in progress.", snapshot
            if self._jobs["module_a"]["status"] == "running" or self._jobs["module_b"]["status"] == "running":
                snapshot = self._snapshot_locked()
                return False, "Finish the active module run before starting Run All.", snapshot
            self._jobs["run_all"] = self._begin_job("run_all", triggered_by_role)

        worker = threading.Thread(
            target=self._run_all_job,
            name="assignment3-run-all",
            daemon=True,
        )
        worker.start()
        return True, "Run All started.", self.snapshot()

    def _start_single_job(self, job_name: str, triggered_by_role: str, runner):
        with self._lock:
            if self._jobs["run_all"]["status"] == "running":
                snapshot = self._snapshot_locked()
                return False, "Run All is in progress. Please wait for it to finish.", snapshot
            if self._jobs[job_name]["status"] == "running":
                snapshot = self._snapshot_locked()
                return False, f"{self._display_name(job_name)} is already running.", snapshot
            self._jobs[job_name] = self._begin_job(job_name, triggered_by_role)

        worker = threading.Thread(
            target=runner,
            name=f"assignment3-{job_name}",
            daemon=True,
        )
        worker.start()
        return True, f"{self._display_name(job_name)} started.", self.snapshot()

    def _run_module_a_job(self):
        self._append_log("module_a", "Visual console requested a Module A verification run.")
        self._append_log("module_a", "Launching assignment3_demo.py in a background subprocess.")
        runtime_dir = Path(tempfile.gettempdir()) / "safedocs-assignment3" / "module_a" / self._job_id("module_a")
        env = os.environ.copy()
        env["SAFEDOCS_A3_RUNTIME_DIR"] = str(runtime_dir)
        self._append_log("module_a", f"Using writable runtime directory: {runtime_dir}.")
        exit_code = self._run_process(
            "module_a",
            [sys.executable, "-u", "assignment3_demo.py"],
            self.module_a_dir,
            env,
        )
        self._finish_job("module_a", exit_code)

    def _run_module_b_job(self):
        self._append_log("module_b", "Visual console requested a Module B stress run.")
        self._append_log("module_b", "Launching stress/assignment3_stress.py in a background subprocess.")
        exit_code = self._run_process(
            "module_b",
            [sys.executable, "-u", "stress/assignment3_stress.py"],
            self.module_b_dir,
            os.environ.copy(),
        )
        self._finish_job("module_b", exit_code)

    def _run_all_job(self):
        self._append_log("run_all", "Run All started from the visual console.")
        self._set_scenario_status("run_all", "Module A", "running")
        self._append_log("run_all", "Starting Module A first.")

        with self._lock:
            self._jobs["module_a"] = self._begin_job("module_a", self._jobs["run_all"]["triggered_by_role"])
        self._run_module_a_job()
        module_a_status = self.snapshot()["module_a"]["status"]
        self._set_scenario_status("run_all", "Module A", "passed" if module_a_status == "passed" else "failed")
        self._append_log("run_all", f"Module A finished with status={module_a_status}.")

        self._set_scenario_status("run_all", "Module B", "running")
        self._append_log("run_all", "Starting Module B next.")
        with self._lock:
            self._jobs["module_b"] = self._begin_job("module_b", self._jobs["run_all"]["triggered_by_role"])
        self._run_module_b_job()
        module_b_status = self.snapshot()["module_b"]["status"]
        self._set_scenario_status("run_all", "Module B", "passed" if module_b_status == "passed" else "failed")
        self._append_log("run_all", f"Module B finished with status={module_b_status}.")

        overall_exit = 0 if module_a_status == "passed" and module_b_status == "passed" else 1
        self._finish_job("run_all", overall_exit)

    def _run_process(self, job_name: str, command: list[str], cwd: Path, env: dict[str, str]):
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self._append_log(job_name, f"Failed to launch subprocess: {exc}")
            return -1

        if process.stdout is not None:
            for line in process.stdout:
                stripped = line.rstrip()
                if stripped:
                    self._append_log(job_name, stripped)

        return process.wait()

    def _append_log(self, job_name: str, line: str):
        with self._lock:
            job = self._jobs[job_name]
            job["logs"].append(line)
            self._parse_log_line(job, line)

    def _parse_log_line(self, job: dict, line: str):
        header_map = {}
        if job["job_name"] == "module_a":
            header_map = MODULE_A_HEADERS
        elif job["job_name"] == "module_b":
            header_map = MODULE_B_HEADERS

        for prefix, scenario_name in header_map.items():
            if line.startswith(prefix):
                job["scenario_results"][scenario_name] = "running"
                job["current_scenario"] = scenario_name
                return

        if line.startswith("[PASS] "):
            scenario_name = line[7:].split(":", 1)[0].strip()
            if scenario_name in job["scenario_results"]:
                job["scenario_results"][scenario_name] = "passed"
                if job["current_scenario"] == scenario_name:
                    job["current_scenario"] = None
            return

        if line.startswith("[FAIL] "):
            scenario_name = line[7:].split(":", 1)[0].strip()
            if scenario_name in job["scenario_results"]:
                job["scenario_results"][scenario_name] = "failed"
                if job["current_scenario"] == scenario_name:
                    job["current_scenario"] = None

    def _finish_job(self, job_name: str, exit_code: int):
        with self._lock:
            job = self._jobs[job_name]
            finished_at = self._utc_now()
            job["finished_at"] = finished_at
            job["exit_code"] = exit_code
            started_at = datetime.datetime.fromisoformat(job["started_at"])
            finished_at_dt = datetime.datetime.fromisoformat(finished_at)
            job["duration_seconds"] = round((finished_at_dt - started_at).total_seconds(), 2)
            if exit_code == 0:
                job["status"] = "passed"
            else:
                job["status"] = "failed"
                current = job.get("current_scenario")
                if current and job["scenario_results"].get(current) == "running":
                    job["scenario_results"][current] = "failed"
            job["current_scenario"] = None

    def _set_scenario_status(self, job_name: str, scenario_name: str, status: str):
        with self._lock:
            job = self._jobs[job_name]
            if scenario_name in job["scenario_results"]:
                job["scenario_results"][scenario_name] = status
                job["current_scenario"] = scenario_name if status == "running" else job.get("current_scenario")
                if status != "running" and job.get("current_scenario") == scenario_name:
                    job["current_scenario"] = None

    def _begin_job(self, job_name: str, triggered_by_role: str):
        return {
            "job_name": job_name,
            "job_id": uuid.uuid4().hex[:12],
            "status": "running",
            "started_at": self._utc_now(),
            "finished_at": None,
            "duration_seconds": None,
            "exit_code": None,
            "triggered_by_role": triggered_by_role,
            "logs": [],
            "scenario_results": self._scenario_template(job_name),
            "current_scenario": None,
        }

    def _new_job(self, job_name: str):
        job = self._begin_job(job_name, triggered_by_role="")
        job["status"] = "idle"
        job["started_at"] = None
        job["job_id"] = None
        return job

    def _job_id(self, job_name: str):
        with self._lock:
            return self._jobs[job_name]["job_id"] or uuid.uuid4().hex[:12]

    def _scenario_template(self, job_name: str):
        scenario_names = {
            "module_a": MODULE_A_SCENARIOS,
            "module_b": MODULE_B_SCENARIOS,
            "run_all": RUN_ALL_SCENARIOS,
        }[job_name]
        return {name: "pending" for name in scenario_names}

    def _public_job_state(self, job: dict):
        return copy.deepcopy(
            {
                "job_name": job["job_name"],
                "job_id": job["job_id"],
                "status": job["status"],
                "started_at": job["started_at"],
                "finished_at": job["finished_at"],
                "duration_seconds": job["duration_seconds"],
                "exit_code": job["exit_code"],
                "triggered_by_role": job["triggered_by_role"],
                "logs": job["logs"],
                "scenario_results": job["scenario_results"],
            }
        )

    def _snapshot_locked(self):
        return {name: self._public_job_state(job) for name, job in self._jobs.items()}

    def _display_name(self, job_name: str):
        return {
            "module_a": "Module A",
            "module_b": "Module B",
            "run_all": "Run All",
        }[job_name]

    def _utc_now(self):
        return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
