import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from ml_experiments.db import session_factory
from ml_experiments.experiment_worker import claim_one, recover_stale
from ml_experiments.models import SourceLdaRun


@unittest.skipUnless(os.getenv("ML_DATABASE_URL"), "A migrated disposable database is required")
class WorkerTests(unittest.TestCase):
    def make_run(self):
        with session_factory()() as session:
            with session.begin():
                run = SourceLdaRun(manifest_id=uuid.uuid4(), target_participant_id=uuid.uuid4(),
                                   status="queued", correlation_id="worker-test", trace_context={})
                session.add(run)
                session.flush()
                return run.id

    def test_workers_claim_distinct_jobs_and_recover_stale(self):
        first, second = self.make_run(), self.make_run()
        with ThreadPoolExecutor(max_workers=2) as pool:
            claimed = set(pool.map(lambda _: claim_one(), range(2)))
        self.assertEqual({first, second}, claimed)
        with session_factory()() as session:
            with session.begin():
                session.execute(text("""UPDATE ml_experiments.source_lda_runs SET status='failed',
                    completed_at=clock_timestamp(), error='test complete' WHERE id IN (:a, :b)"""), {"a": first, "b": second})
        stale = self.make_run()
        with session_factory()() as session:
            with session.begin():
                session.execute(text("""UPDATE ml_experiments.source_lda_runs SET status='running',
                    started_at=clock_timestamp()-interval '10 minutes', heartbeat_at=clock_timestamp()-interval '10 minutes'
                    WHERE id=:id"""), {"id": stale})
        self.assertGreaterEqual(recover_stale(), 1)
        with session_factory()() as session:
            self.assertEqual("interrupted", session.get(SourceLdaRun, stale).status)


if __name__ == "__main__":
    unittest.main()
