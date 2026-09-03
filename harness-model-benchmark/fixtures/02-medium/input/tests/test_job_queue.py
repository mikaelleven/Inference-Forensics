import unittest
from job_queue import Job, JobQueue


class JobQueueTests(unittest.TestCase):
    def test_higher_priority_ready_job_runs_first(self):
        queue = JobQueue()
        queue.enqueue(Job("low", priority=1))
        queue.enqueue(Job("high", priority=10))
        self.assertEqual(["high", "low"], [job.id for job in queue.ready()])

    def test_dependency_blocks_job_until_completed(self):
        queue = JobQueue()
        queue.enqueue(Job("build"))
        queue.enqueue(Job("deploy", depends_on=("build",)))
        self.assertEqual(["build"], [job.id for job in queue.ready()])
        queue.complete("build")
        self.assertEqual(["deploy"], [job.id for job in queue.ready()])


if __name__ == "__main__":
    unittest.main()
