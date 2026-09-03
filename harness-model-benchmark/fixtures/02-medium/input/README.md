# Job Queue

`JobQueue` stores active jobs and returns the jobs that are ready to run.

## Rules

- A job is identified by a unique `id` while it is active.
- Enqueuing a duplicate active `id` raises `ValueError` and must not replace the original job.
- A job is ready only when **all** ids in `depends_on` have been completed.
- An unknown dependency is not satisfied.
- Ready jobs are ordered by higher `priority` first.
- Jobs with the same priority preserve enqueue order (FIFO).
- `complete(job_id)` marks an active job complete and removes it from the active queue.
- Completing an unknown/non-active job raises `KeyError`.

## Public API

```python
Job(id: str, priority: int = 0, depends_on: tuple[str, ...] = ())
JobQueue.enqueue(job) -> None
JobQueue.ready() -> list[Job]
JobQueue.complete(job_id) -> None
```
