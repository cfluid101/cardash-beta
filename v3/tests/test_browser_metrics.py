import tempfile
import types
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import Receiver

class BrowserMetricsTest(unittest.TestCase):
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
