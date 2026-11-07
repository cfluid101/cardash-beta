import tempfile
import types
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import Receiver

class BrowserMetricsTest(unittest.TestCase):
 def test_distinct_browser_metrics_are_rate_limited_with_bounded_client_slots(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Receiver(types.SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.log=Mock()
   data={'browserInstance':'a'*32,'heartbeatRttMs':25.2,'statusRttMs':100,'inputRttMs':45,'inputQueued':5,'inputCoalesced':100,'inputErrors':1,'heartbeatErrors':2,'videoRetries':3,'streamLagMs':4250.2,'streamRecoveries':2}
   with patch('server.time.monotonic',return_value=100):
    r.browser_metrics(data);r.browser_metrics(data);r.browser_metrics({**data,'browserInstance':'b'*32})
    for i in range(14):r.browser_metrics({**data,'browserInstance':f'{i:032x}'})
    r.browser_metrics({**data,'browserInstance':'f'*32})
   self.assertEqual(r.log.call_count,16);self.assertEqual(r.log.call_args_list[0].kwargs,data)
   with patch('server.time.monotonic',return_value=701):r.browser_metrics({**data,'browserInstance':'f'*32})
   self.assertEqual(r.log.call_count,17)
 def test_new_diagnostics_reject_invalid_ids_nonfinite_latency_and_noninteger_counts(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Receiver(types.SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.log=Mock()
   for value in ({'browserInstance':'secret-token'},{'heartbeatRttMs':float('inf')},{'statusRttMs':60001},{'inputQueued':6},{'inputCoalesced':1.5},{'inputErrors':True},{'heartbeatErrors':-1},{'videoRetries':10**10+1},{'streamLagMs':-1},{'streamRecoveries':True}):r.browser_metrics(value)
   r.log.assert_not_called()
 def test_metrics_are_bounded_numeric_only_and_rate_limited(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Receiver(types.SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.log=Mock()
   valid={'width':1800,'height':700,'decodedFrames':120,'droppedFrames':3,'currentTime':4.2,'paused':True,'hidden':False,'readyState':4,'mediaError':0,'secureContext':False,'webCodecs':True,'webGL':True,'webGPU':False,'renderer':'jpeg-canvas','presentedFrames':115,'frameAgeMs':24.5,'decoderQueueSize':2}
   with patch('server.time.monotonic',return_value=100):
    r.browser_metrics({**valid,'privateKey':'must-not-log','source':'secret-url','videoErrors':float('nan')})
    r.browser_metrics(valid)
   self.assertEqual(r.log.call_count,1)
   self.assertEqual(r.log.call_args.args,('browser_metrics',))
   self.assertEqual(r.log.call_args.kwargs,valid)
   with patch('server.time.monotonic',return_value=120):
    r.browser_metrics({'width':10**10,'paused':'wrong','privateKey':'secret','webGPU':'yes','renderer':'secret-url','presentedFrames':-1,'frameAgeMs':float('inf'),'decoderQueueSize':10001})
   self.assertEqual(r.log.call_count,1)

if __name__=='__main__':unittest.main()
