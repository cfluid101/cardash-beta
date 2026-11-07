# SPDX-License-Identifier: GPL-3.0-only
"""Scoped access for the owned HTTPS frontend; local cookie access is separate.

This preserves the trusted-hotspot model: any permitted local peer can already
open the local page. An exact trusted website can bootstrap its own controller
token; this is not device-owner authentication. Pages paths are not origins, so
all content on this GitHub account's Pages origin must be trusted.
"""
import hmac
import re
import secrets
import time

TRUSTED_ORIGIN='https://cfluid101.github.io'
IDLE_SECONDS=1800
MAX_CLIENTS=16
ROUTES={
 '/api/browser_session':frozenset(('POST',)),
 '/api/status':frozenset(('GET','POST')),
 **{('/api/'+name):frozenset(('POST',)) for name in ('start','stop','resize','heartbeat','touch','audio_output')},
 '/video':frozenset(('GET',)), '/audio':frozenset(('GET',)), '/image':frozenset(('GET',)),
}
ALLOWED_HEADERS=frozenset(('authorization','content-type','x-cardash-session','x-cardash-frame'))


class BrowserAccessError(ValueError):
 def __init__(self,message,status=403):
  super().__init__(message);self.status=status


def require(value,message,status=403):
 if not value:raise BrowserAccessError(message,status)


class BrowserAccess:
 def __init__(self,clock=None):
  self.clock=clock or time.monotonic;self.clients={}
 @staticmethod
 def trusted(origin):return origin==TRUSTED_ORIGIN
 @staticmethod
 def allowed(method,path):return method in ROUTES.get(path,())
 @staticmethod
 def response_headers(origin):
  require(origin==TRUSTED_ORIGIN,'Cross-origin request rejected')
  return {'Access-Control-Allow-Origin':origin,'Vary':'Origin','Access-Control-Expose-Headers':'X-CarDash-Frame, X-CarDash-Time'}
 def preflight(self,origin,path,method,requested):
  result=self.response_headers(origin)
  require(self.allowed(method,path),'Cross-origin route or method rejected')
  require(isinstance(requested,str) and len(requested)<=256,'Preflight header limit')
  names=[v.strip().lower() for v in requested.split(',')] if requested else []
  require(len(names)<=len(ALLOWED_HEADERS) and len(names)==len(set(names)) and all(v in ALLOWED_HEADERS for v in names),'Preflight headers rejected')
  result.update({'Access-Control-Allow-Methods':method,'Access-Control-Max-Age':'300'})
  if names:result['Access-Control-Allow-Headers']=', '.join(sorted(names))
  return result
 def prune(self,now):
  for key,value in list(self.clients.items()):
   if now-value['lastUsed']>=IDLE_SECONDS:del self.clients[key]
 def issue(self,origin,value):
  require(self.trusted(origin),'Cross-origin request rejected')
  require(isinstance(value,dict) and set(value)=={'version','clientId'} and type(value.get('version')) is int and value['version']==1,'Unsupported browser session request',400)
  client=value['clientId'];require(isinstance(client,str) and re.fullmatch('[0-9a-f]{32}',client),'Invalid browser client identifier',400)
  now=self.clock();self.prune(now);key=(origin,client);record=self.clients.get(key)
  if record is None:
   require(len(self.clients)<MAX_CLIENTS,'Too many browser controllers; close idle pages and retry later',429)
   record={'token':secrets.token_hex(32),'lastUsed':now};self.clients[key]=record
  record['lastUsed']=now
  return {'version':1,'token':record['token'],'expiresIn':IDLE_SECONDS}
 def authorize(self,origin,authorization):
  require(self.trusted(origin),'Cross-origin request rejected')
  require(isinstance(authorization,str) and re.fullmatch('Bearer [0-9a-f]{64}',authorization),'Reconnect the HTTPS page to authorize this browser',401)
  token=authorization[7:];now=self.clock();self.prune(now)
  for (allowed_origin,_),record in self.clients.items():
   if allowed_origin==origin and hmac.compare_digest(record['token'],token):
    record['lastUsed']=now;return
  raise BrowserAccessError('Browser authorization expired; reconnect the HTTPS page',401)
