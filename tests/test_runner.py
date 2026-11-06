import json,os,socket,subprocess,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'build/host/cardash-diagnostics'

class RunnerTests(unittest.TestCase):
    def start(self,mode='normal'):
        self.assertTrue(BIN.is_file(),'Diagnostic runner has not been implemented/built')
        tmp=tempfile.TemporaryDirectory(prefix='cddiag-',dir='/tmp');self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);env=dict(os.environ,CD_DIAG_ROOT=str(root),CD_TEST_WORKER_MODE=mode)
        proc=subprocess.Popen([str(BIN),'--host-daemon'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        def close():
            if proc.poll() is None:proc.terminate()
            try:proc.communicate(timeout=7)
            except subprocess.TimeoutExpired:proc.kill();proc.communicate();self.fail('helper did not shut down')
        self.addCleanup(close)
        for _ in range(100):
            if (root/'control.sock').exists():break
            self.assertIsNone(proc.poll(),'helper exited before socket setup');time.sleep(.02)
        return root,proc
    def command(self,root,cmd):
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(3);s.connect(str(root/'control.sock'));s.sendall((cmd+'\n').encode());data=b''
            while b'\n' not in data:
                part=s.recv(4096)
                if not part:break
                data+=part
            return json.loads(data)
    def finish(self,root):
        for _ in range(200):
            s=self.command(root,'STATUS')
            if not s['running']:
                rows=[json.loads(x) for x in (root/s['report']).read_text().splitlines()]
                self.assertEqual(rows[-1]['event'],'run_end');return rows
            time.sleep(.03)
        self.fail('suite deadline did not finish')
    def test_repeat_runs_are_separate_logs_and_single_controller(self):
        root,_=self.start();a=self.command(root,'RUN');self.assertTrue(a['running'])
        self.assertEqual(self.command(root,'RUN')['report'],a['report'])
        rows=self.finish(root);self.assertTrue(any(x['event']=='worker_exit' for x in rows));self.assertFalse(rows[-1]['live_carplay_verified'])
        b=self.command(root,'RUN');self.assertNotEqual(a['report'],b['report']);self.finish(root)
        self.assertTrue((root/a['report']).is_file());self.assertEqual(self.command(root,'RUN ../../bad')['error'],'unknown command')
    def test_cancel_kills_and_reaps_only_owned_worker(self):
        root,_=self.start('hang');self.command(root,'RUN');time.sleep(.15);self.command(root,'CANCEL');rows=self.finish(root)
        exits=[x for x in rows if x['event']=='worker_exit'];self.assertTrue(exits);self.assertTrue(rows[-1]['cancelled'])
        for x in exits:
            with self.assertRaises(ProcessLookupError):os.kill(x['pid'],0)
    def test_hung_stage_has_a_deadline_and_terminal_report(self):
        root,_=self.start('hang');self.command(root,'RUN');rows=self.finish(root)
        self.assertTrue(any(x.get('timed_out') for x in rows if x['event']=='worker_exit'))
    def test_crashed_worker_is_reported_without_claiming_success(self):
        root,_=self.start('crash');self.command(root,'RUN');rows=self.finish(root)
        self.assertTrue(any(x.get('signal',0)!=0 for x in rows if x['event']=='worker_exit'));self.assertFalse(rows[-1]['live_carplay_verified'])
    def test_noisy_worker_cannot_remove_terminal_summary(self):
        root,_=self.start('noisy');self.command(root,'RUN');rows=self.finish(root)
        self.assertTrue(any(x['event']=='output_truncated' for x in rows));self.assertLess((root/self.command(root,'STATUS')['report']).stat().st_size,7*1024*1024)
    def test_installer_rejects_hardlinked_log_without_changing_target(self):
        self.assertTrue(BIN.is_file())
        with tempfile.TemporaryDirectory(prefix='cddiag-',dir='/tmp') as d:
            root=Path(d);target=root/'unrelated';target.write_text('preserve me');target.chmod(0o600)
            os.link(target,root/'installation.log');env=dict(os.environ,CD_DIAG_ROOT=d)
            p=subprocess.run([str(BIN),'--prepare'],env=env,capture_output=True)
            self.assertNotEqual(p.returncode,0);self.assertEqual(target.read_text(),'preserve me');self.assertEqual(target.stat().st_mode&0o777,0o600)
    def test_installer_prepares_only_its_own_files(self):
        self.assertTrue(BIN.is_file())
        with tempfile.TemporaryDirectory(prefix='cddiag-',dir='/tmp') as d:
            p=subprocess.run([str(BIN),'--prepare'],env=dict(os.environ,CD_DIAG_ROOT=d),capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr.decode());self.assertEqual({x.name for x in Path(d).iterdir()},{'installation.log','helper-bootstrap.log'})
    def test_replaced_directory_cannot_redirect_privileged_report_write(self):
        root,_=self.start();parent=root.parent;kept=parent/(root.name+'-kept');elsewhere=parent/(root.name+'-unrelated');elsewhere.mkdir();root.rename(kept);root.symlink_to(elsewhere,target_is_directory=True)
        import shutil
        self.addCleanup(lambda:shutil.rmtree(kept,ignore_errors=True));self.addCleanup(lambda:shutil.rmtree(elsewhere,ignore_errors=True));self.addCleanup(root.unlink)
        reply=self.command(kept,'RUN')
        self.assertFalse(reply.get('running'));self.assertTrue(reply.get('error'));self.assertEqual(list(elsewhere.iterdir()),[])
    def test_helper_death_cannot_leave_an_orphan_worker(self):
        root,helper=self.start('hang');start=self.command(root,'RUN');pid=None
        for _ in range(80):
            path=root/start['report']
            if path.exists():
                rows=[json.loads(x) for x in path.read_text().splitlines()]
                found=[x['pid'] for x in rows if x['event']=='worker_start']
                if found:pid=found[0];break
            time.sleep(.02)
        self.assertIsNotNone(pid);helper.kill();helper.communicate(timeout=3)
        try:
            for _ in range(100):
                try:os.kill(pid,0)
                except ProcessLookupError:break
                time.sleep(.02)
            else:self.fail('orphan worker survived helper death')
        finally:
            try:os.killpg(pid,9)
            except ProcessLookupError:pass
    def test_helper_death_also_terminates_owned_descendants(self):
        root,helper=self.start('descendant');start=self.command(root,'RUN');pids=[]
        try:
            for _ in range(100):
                path=root/start['report']
                if path.exists():
                    rows=[json.loads(x) for x in path.read_text().splitlines()]
                    leaders=[x['pid'] for x in rows if x['event']=='worker_start']
                    for x in rows:
                        if x['event']=='captured_output':
                            try:inner=json.loads(x['text'])
                            except ValueError:continue
                            if inner.get('event')=='owned_descendant':pids=[leaders[0],inner['pid']]
                    if pids:break
                time.sleep(.01)
            self.assertEqual(len(pids),2);helper.kill();helper.communicate(timeout=3)
            for pid in pids:
                for _ in range(100):
                    try:os.kill(pid,0)
                    except ProcessLookupError:break
                    time.sleep(.02)
                else:self.fail('owned descendant survived helper death')
        finally:
            if pids:
                try:os.killpg(pids[0],9)
                except ProcessLookupError:pass
    def test_cancellation_during_baseline_prevents_start_call(self):
        root,_=self.start('cancel-baseline');start=self.command(root,'RUN')
        for _ in range(100):
            path=root/start['report']
            if path.exists() and 'baseline_enter' in path.read_text():break
            time.sleep(.01)
        self.command(root,'CANCEL');rows=self.finish(root);text=json.dumps(rows)
        self.assertIn('baseline_enter',text);self.assertNotIn('start_call_enter',text);self.assertIn('request_withheld_cancelled',text)
    def test_partial_command_has_total_deadline_even_with_trickled_bytes(self):
        root,_=self.start()
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(.04);s.connect(str(root/'control.sock'));start=time.monotonic();data=b''
            while time.monotonic()-start<.75:
                try:s.sendall(b'S')
                except BrokenPipeError:pass # The server may have closed after queuing its reply; drain it.
                try:
                    data+=s.recv(1024)
                    if b'\n' in data:break
                except socket.timeout:pass
                time.sleep(.08)
            self.assertIn(b'incomplete command',data,'trickled input extended the command deadline')
            self.assertLess(time.monotonic()-start,.65)

if __name__=='__main__':unittest.main()
