import sys,json,plistlib,base64
raw=sys.stdin.buffer.read(1048577)
if len(raw)>1048576:raise ValueError('plist limit')
def pack(x,depth=0):
 if depth>32:raise ValueError('depth')
 if isinstance(x,bytes):return {'$bytes':base64.b64encode(x).decode()}
 if isinstance(x,int) and not isinstance(x,bool) and abs(x)>9007199254740991:return {'$integer':str(x)}
 if isinstance(x,dict):return {k:pack(v,depth+1) for k,v in x.items()}
 if isinstance(x,list):return [pack(v,depth+1) for v in x]
 return x
def unpack(x,depth=0):
 if depth>32:raise ValueError('depth')
 if isinstance(x,dict):
  if list(x)==['$bytes']:return base64.b64decode(x['$bytes'],validate=True)
  if list(x)==['$integer']:return int(x['$integer'])
  return {k:unpack(v,depth+1) for k,v in x.items()}
 if isinstance(x,list):return [unpack(v,depth+1) for v in x]
 return x
if sys.argv[1]=='decode':sys.stdout.write(json.dumps(pack(plistlib.loads(raw))))
else:sys.stdout.buffer.write(plistlib.dumps(unpack(json.loads(raw)),fmt=plistlib.FMT_BINARY,sort_keys=False))
