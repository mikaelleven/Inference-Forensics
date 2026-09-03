import unittest
from job_queue import Job, JobQueue


class HiddenJobQueueTests(unittest.TestCase):
    def test_fifo_with_equal_priority(self):
        queue = JobQueue()
        queue.enqueue(Job("a", priority=5))
        queue.enqueue(Job("b", priority=5))
        queue.enqueue(Job("c", priority=5))
        self.assertEqual(["a", "b", "c"], [job.id for job in queue.ready()])

    def test_duplicate_active_id_raises_without_replacing_original(self):
        queue = JobQueue()
        queue.enqueue(Job("same", priority=1))
        with self.assertRaises(ValueError):
            queue.enqueue(Job("same", priority=99))
        self.assertEqual(1, queue.ready()[0].priority)

    def test_unknown_dependency_is_not_ready(self):
        queue = JobQueue()
        queue.enqueue(Job("deploy", depends_on=("missing",)))
        self.assertEqual([], queue.ready())

    def test_all_dependencies_must_be_completed(self):
        queue = JobQueue()
        queue.enqueue(Job("a"))
        queue.enqueue(Job("b"))
        queue.enqueue(Job("final", priority=100, depends_on=("a", "b")))
        queue.complete("a")
        self.assertNotIn("final", [job.id for job in queue.ready()])
        queue.complete("b")
        self.assertEqual(["final"], [job.id for job in queue.ready()])

    def test_completed_job_can_be_enqueued_again(self):
        queue = JobQueue()
        queue.enqueue(Job("job"))
        queue.complete("job")
        queue.enqueue(Job("job", priority=2))
        self.assertEqual(["job"], [job.id for job in queue.ready()])

    def test_complete_unknown_raises(self):
        queue = JobQueue()
        with self.assertRaises(KeyError):
            queue.complete("missing")


if __name__ == "__main__":
    unittest.main()
