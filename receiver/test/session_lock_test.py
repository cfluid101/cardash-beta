import importlib.util
import multiprocessing
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

class LockTest(unittest.TestCase):
    def test_second_process_cannot_replace_active_trial_and_crash_releases_lock(self):
        self.assertIsNotNone(importlib.util.find_spec('session_lock'), 'Missing single-session guard')
        from session_lock import SessionLock, active_trial
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with SessionLock(root) as lock:
                lock.publish(root / 'first')
                self.assertEqual(active_trial(root), root / 'first')
                ctx = multiprocessing.get_context('fork')
                q = ctx.Queue()
                def compete():
                    try:
                        with SessionLock(root):
                            q.put('acquired')
                    except BlockingIOError:
                        q.put('busy')
                p = ctx.Process(target=compete); p.start(); p.join(3)
                self.assertEqual(q.get(timeout=1), 'busy')
                self.assertEqual(active_trial(root), root / 'first')
            self.assertIsNone(active_trial(root))
            with SessionLock(root) as lock:
                lock.publish(root / 'second')
                self.assertEqual(active_trial(root), root / 'second')

if __name__ == '__main__':
    unittest.main()
