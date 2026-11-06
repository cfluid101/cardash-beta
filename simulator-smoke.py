#!/usr/bin/env python3
"""Exercise the app's real Run and Share handlers against an owned host helper.
Native CarPlay is never attempted by this simulator fixture.
"""
from pathlib import Path
import json,os,subprocess,tempfile,time
ROOT=Path(__file__).resolve().parent
SET=ROOT.parents[1]/'build-v2/offline-carplay-lab-01/simulator-devices'
DEVICE='3DD049BD-C0F1-4559-9EB1-135F769F861B'
BUNDLE='com.cfluid.cardash.diagnostics.app'
def sim(*args,env=None):
    return subprocess.check_output(['xcrun','simctl','--set',str(SET),*args],env=env,text=True).strip()
with tempfile.TemporaryDirectory(prefix='cddiag-ui-',dir='/tmp') as folder:
    env=dict(os.environ,CD_DIAG_ROOT=folder,CD_TEST_WORKER_MODE='normal')
    helper=subprocess.Popen([str(ROOT/'build/host/cardash-diagnostics'),'--host-daemon'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            if (Path(folder)/'control.sock').exists():break
            time.sleep(.03)
        sim('install',DEVICE,str(ROOT/'build/simulator/CarDashDiagnostics.app'))
        env=dict(os.environ,SIMCTL_CHILD_CD_DIAG_ROOT=folder,SIMCTL_CHILD_CD_SIM_AUTORUN='1',SIMCTL_CHILD_CD_SIM_AUTOEXPORT='1')
        sim('launch','--terminate-running-process',DEVICE,BUNDLE,env=env)
        container=Path(sim('get_app_container',DEVICE,BUNDLE,'data'));result=container/'Documents/smoke.json'
        for _ in range(150):
            if result.exists():break
            time.sleep(.2)
        data=json.loads(result.read_text());assert not data['helper_error'],data;assert data['report_bytes']>500,data
        report=Path(data['export']);rows=[json.loads(line) for line in report.read_text().splitlines()]
        assert rows[0]['event']=='app_export';assert any(x['event']=='run_end' for x in rows);assert not data['native_carplay_attempted']
        (ROOT/'evidence/simulator-export.log').write_bytes(report.read_bytes())
        (ROOT/'evidence/simulator-smoke.json').write_text(json.dumps(data,indent=2)+'\n')
        sim('io',DEVICE,'screenshot',str(ROOT/'evidence/simulator-share.png'))
        print(json.dumps({'passed':True,'log_lines':len(rows),'app_status':data['ui_status'],'native_carplay_attempted':False},indent=2))
    finally:
        helper.terminate()
        try:helper.communicate(timeout=6)
        except subprocess.TimeoutExpired:helper.kill();helper.communicate()
        subprocess.run(['xcrun','simctl','--set',str(SET),'terminate',DEVICE,BUNDLE],capture_output=True)
