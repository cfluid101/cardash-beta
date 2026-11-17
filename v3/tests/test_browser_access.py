import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from browser_access import BrowserAccess, BrowserAccessError, TRUSTED_ORIGIN


class BrowserAccessTest(unittest.TestCase):
 def setUp(self):
  self.now=100.0
  self.access=BrowserAccess(clock=lambda:self.now)
 def bootstrap(self,client='a'*32,origin=TRUSTED_ORIGIN):
  return self.access.issue(origin,{'version':1,'clientId':client})
 def test_origin_bound_token_and_reload_reuse(self):
  first=self.bootstrap();self.assertEqual(first['version'],1);self.assertEqual(first['expiresIn'],1800)
  self.assertEqual(len(first['token']),64);self.assertEqual(first,self.bootstrap())
  self.access.authorize(TRUSTED_ORIGIN,'Bearer '+first['token'])
  for origin in ('https://unrelated.invalid','https://cfluid101.github.io.evil.invalid','null','http://cfluid101.github.io'):
   with self.subTest(origin=origin),self.assertRaises(BrowserAccessError):self.access.authorize(origin,'Bearer '+first['token'])
 def test_idle_expiry_refresh_and_bounded_slots(self):
  token=self.bootstrap()['token'];self.now+=1799;self.access.authorize(TRUSTED_ORIGIN,'Bearer '+token)
  self.now+=1799;self.access.authorize(TRUSTED_ORIGIN,'Bearer '+token)
  self.now+=1801
  with self.assertRaises(BrowserAccessError) as error:self.access.authorize(TRUSTED_ORIGIN,'Bearer '+token)
  self.assertEqual(error.exception.status,401)
  for i in range(16):self.bootstrap(f'{i:032x}')
  with self.assertRaises(BrowserAccessError) as error:self.bootstrap('f'*32)
  self.assertEqual(error.exception.status,429)
  self.now+=1801;self.assertEqual(len(self.bootstrap('f'*32)['token']),64)
 def test_bootstrap_validation_and_no_token_reuse_across_service(self):
  for body in (None,[],{}, {'version':True,'clientId':'a'*32},{'version':2,'clientId':'a'*32},{'version':1,'clientId':'bad'}, {'version':1,'clientId':'a'*32,'origin':TRUSTED_ORIGIN}):
   with self.subTest(body=body),self.assertRaises(BrowserAccessError):self.access.issue(TRUSTED_ORIGIN,body)
  token=self.bootstrap()['token']
  with self.assertRaises(BrowserAccessError):BrowserAccess().authorize(TRUSTED_ORIGIN,'Bearer '+token)
 def test_preflight_is_route_method_and_header_scoped(self):
  headers=self.access.preflight(TRUSTED_ORIGIN,'/video','GET','authorization, x-cardash-session')
  self.assertEqual(headers['Access-Control-Allow-Origin'],TRUSTED_ORIGIN)
  self.assertEqual(headers['Access-Control-Allow-Methods'],'GET')
  self.assertNotIn('Access-Control-Allow-Credentials',headers)
  self.assertEqual(headers['Vary'],'Origin')
  for path,method,names in [('/video','POST','authorization'),('/api/prepare','POST','content-type'),('/api/report','POST','authorization'),('/api/browser_session','GET',''),('/video','GET','authorization, x-unapproved'),('/video?token=secret','GET','authorization')]:
   with self.subTest(path=path,method=method,names=names),self.assertRaises(BrowserAccessError):self.access.preflight(TRUSTED_ORIGIN,path,method,names)


if __name__=='__main__':unittest.main()
