"""Bound native encoder demand to the browser link, not the internal loopback."""
import math
from transport import AudioLease, MachClock, notification_state

class VideoBudget:
    def __init__(self):
        self.bps=3000000;self.last=-float('inf');self.healthy_since=None
    def feedback(self,value,now):
        if not isinstance(value,dict) or value.get('hidden') is True:return
        rtt,lag=value.get('heartbeatRttMs'),value.get('streamLagMs')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (rtt,lag)):return
        if now-self.last<1.5:return
        self.last=now
        if rtt>450 or (value.get('frameReady') is not False and lag>700):
            self.bps=max(750000,int(self.bps*.65));self.healthy_since=None
        elif value.get('frameReady') is not False and rtt<250 and lag<250:
            if self.healthy_since is None:self.healthy_since=now
            if now-self.healthy_since>=20:
                self.bps=min(3000000,self.bps+150000);self.healthy_since=now
        else:self.healthy_since=None

class VideoBudgetLease(AudioLease):
    def refresh(self,bps):
        if type(bps) is not int or not 750000<=bps<=6000000:raise ValueError('Invalid encoder budget')
        if self.clock is None:self.clock=MachClock()
        self.write(b'com.cfluid.cardash.v3.video.lease',int(self.clock()*1000))
        self.write(b'com.cfluid.cardash.v3.video.request',(self.pid<<32)|bps)
    def clear(self):
        if not self.tokens:return
        self.write(b'com.cfluid.cardash.v3.video.request',0)
        self.write(b'com.cfluid.cardash.v3.video.lease',0)

def budget_status():
    result={'ready':False}
    try:
        value=notification_state(b'com.cfluid.cardash.v3.video.ready')
        result.update(pid=value>>8,code=value&255)
        state=notification_state(b'com.cfluid.cardash.v3.video.state')
        observed=notification_state(b'com.cfluid.cardash.v3.video.observed')
        return {'ready':value&255==1,'pid':value>>8,'code':value&255,'requestedBps':state&0xffffffff,
                'nativeBps':observed>>32,'appliedBps':observed&0xffffffff}
    except (OSError,AttributeError) as error:
        result['error']=str(error);return result
