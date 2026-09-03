from __future__ import annotations
from dataclasses import dataclass
from .models import Job


@dataclass
class _QueuedJob:
    job: Job
    sequence: int


class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, _QueuedJob] = {}
        self._completed: set[str] = set()
        self._sequence = 0

    def enqueue(self, job: Job) -> None:
        self._jobs[job.id] = _QueuedJob(job=job, sequence=self._sequence)
        self._sequence += 1

    def ready(self) -> list[Job]:
        ready = [
            queued
            for queued in self._jobs.values()
            if all(dep in self._jobs or dep in self._completed for dep in queued.job.depends_on)
        ]
        ready.sort(key=lambda queued: (queued.job.priority, queued.sequence))
        return [queued.job for queued in ready]

    def complete(self, job_id: str) -> None:
        if job_id not in self._jobs:
            raise KeyError(job_id)
        del self._jobs[job_id]
        self._completed.add(job_id)
