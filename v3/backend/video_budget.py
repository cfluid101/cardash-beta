"""Bound native encoder demand to the browser link, not the internal loopback."""
import math
from transport import AudioLease, MachClock, notification_state

VIDEO_READY_REASONS={
    0:'ready',
    1:'entry_address_overflow',
    2:'hook_provider_unavailable',
    3:'required_symbols_unavailable',
    4:'entry_mapping_mismatch',
    5:'entry_prologue_mismatch',
    6:'property_key_type_mismatch',
    7:'copy_property_symbols_or_key_mismatch',
    8:'hook_installation_failed',
    9:'unsupported_image_identity_or_header',
    10:'arm64e_adapter_slice_required',
}

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
        result={'ready':value&255==1,'pid':value>>8,'code':value&255,'requestedBps':state&0xffffffff,
                'nativeBps':observed>>32,'appliedBps':observed&0xffffffff}
    except (OSError,AttributeError) as error:
        result['error']=str(error);return result
    # Optional: older adapters publish only the original ready channel. A stale
    # PID/status, missing registration or readiness transition supplies no reason
    # and must not turn a valid existing readiness result into a failure.
    try:
        reason=notification_state(b'com.cfluid.cardash.v3.video.ready_reason')
        reason_pid,reason_status,reason_code=reason>>32,(reason>>16)&0xffff,reason&0xffff
        if (result['pid']>1 and reason_pid==result['pid'] and reason_status==result['code'] and
            reason_status in (1,2) and (reason_status==1)==(reason_code==0) and
            notification_state(b'com.cfluid.cardash.v3.video.ready')==value):
            result.update(reasonCode=reason_code,reason=VIDEO_READY_REASONS.get(reason_code,'unknown_reason'))
    except (OSError,AttributeError):pass
    return result
