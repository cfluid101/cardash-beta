from pathlib import Path
import subprocess,sys,time,json,hashlib,os,signal
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'evidence/device-0.1.2-20261106-ssh'))
from ssh_client import SSH,remote
trial=ROOT/'evidence/receiver-live'/time.strftime('%Y%m%d-%H%M%S');trial.mkdir(parents=True,mode=0o700)
state=ROOT/'evidence/receiver-identity';state.mkdir(exist_ok=True,mode=0o700)
binpath=ROOT/'build/receiver/session-probe';device='/var/mobile/Media/CarDashDiagnosticsResearch-20261106-2232/session-probe'
remote('cat > '+device+' && chmod 755 '+device,input=binpath.read_bytes())
assert remote('/var/jb/usr/bin/sha256sum '+device).decode().split()[0]==hashlib.sha256(binpath.read_bytes()).hexdigest()
duration=int(sys.argv[1]) if len(sys.argv)>1 else 25
if not 5<=duration<=300:raise ValueError('trial duration must be 5..300 seconds')
(trial/'manifest.json').write_text(json.dumps({'duration':duration,'probe_sha256':hashlib.sha256(binpath.read_bytes()).hexdigest(),'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'receiver').rglob('*') if p.is_file() and 'node_modules' not in p.parts}},indent=2))
processes=[]
def stop_trial(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop_trial)
try:
 receiverLog=(trial/'receiver.ndjson').open('wb');receiver=subprocess.Popen(['node',str(ROOT/'receiver/server.mjs'),str(state),str(trial)],stdout=receiverLog,stderr=subprocess.STDOUT);processes.append(receiver)
 for _ in range(50):
  if b'listening' in (trial/'receiver.ndjson').read_bytes():break
  if receiver.poll() is not None:raise RuntimeError('receiver exited')
  time.sleep(.1)
 else:raise RuntimeError('receiver not ready')
 pub=(state/'public-key.txt').read_text().strip()
 syslog=(trial/'service.log').open('wb');logger=subprocess.Popen(['idevicesyslog','-u','8b396e4f30daebafbd26bd102c9e7ffda535bd33','-x','--no-colors','-p','carkitd|mediaserverd|CarPlay'],stdout=syslog,stderr=subprocess.STDOUT);processes.append(logger)
 output=(trial/'native.ndjson').open('wb')
 forwards=['-L','127.0.0.1:46204:[::1]:62004']
 for phone,host in [(62000,46200),(62001,46201),(62002,46202)]:forwards+=['-R',f'[::1]:{phone}:127.0.0.1:{host}']
 command=SSH[:-1]+['-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',*forwards,SSH[-1],device+' 62000 '+pub+' '+str(duration)]
 client=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT);processes.append(client)
 print('Trial '+str(trial),flush=True)
 try:client.wait(timeout=duration+15)
 except subprocess.TimeoutExpired:client.terminate();client.wait(timeout=5)
 print('Client exit '+str(client.returncode),flush=True)
finally:
 for p in reversed(processes):
  if p.poll() is None:
   p.terminate()
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:p.kill();p.wait()
 (trial/'device-state-after.json').write_bytes(remote('/var/jb/usr/bin/uiopen --bundleid com.cfluid.cardash.v2.host; /var/jb/usr/lib/CarDashV2Lab/device-state'))
with (trial/'combined.ndjson').open('w') as combined:
 for name in ['receiver.ndjson','native.ndjson','service.log']:
  for line in (trial/name).read_text(errors='replace').splitlines():
   try:value=json.loads(line)
   except ValueError:value={'text':line}
   combined.write(json.dumps({'source':name,'record':value})+'\n')
print('Evidence saved: '+str(trial))
