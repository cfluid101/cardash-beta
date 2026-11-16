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
    """Encoder budget driven by evidence that video is not getting through.

    Beta 5 cut 35% whenever one heartbeat round trip exceeded 450 ms. In the
    owner's November 2026 log 45 of 51 cuts happened with nothing waiting to be
    sent and 40 while the stream used under 80% of its budget: a fresh-connection
    heartbeat measures request latency (and this service's own stalls), not
    capacity. Late pictures and unsent video are the congestion signals. A slow
    heartbeat alone needs repetition and a stream that is actually near budget.
    """
    CEILING=3000000;FLOOR=750000;BACKLOG_BYTES=192*1024
    def __init__(self):
        self.bps=self.CEILING;self.last=-float('inf');self.healthy_since=None
        self.cut_at=-float('inf');self.slow=0;self.recover_to=0;self.reason=''
    def cut(self,now,factor,reason):
        # One reduction per congestion event: the encoder and the queued video
        # need a few seconds to reflect it before the same lag is counted again.
        self.healthy_since=None
        if now-self.cut_at<4 or self.bps<=self.FLOOR:return None
        # Remember where the episode started so recovery can return quickly to
        # a rate that worked, then probe slowly beyond it.
        if now-self.cut_at>15:self.recover_to=max(self.FLOOR,int(self.bps*.7))
        self.cut_at=now;self.slow=0;self.bps=max(self.FLOOR,int(self.bps*factor));self.reason=reason
        return reason
    def feedback(self,value,now,queued_bytes=0,measured_bps=None):
        """Apply one browser report. Returns the reason when the budget changed."""
        if not isinstance(value,dict) or value.get('hidden') is True:return None
        rtt,lag=value.get('heartbeatRttMs'),value.get('streamLagMs')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (rtt,lag)):return None
        if now-self.last<1.5:return None
        self.last=now
        presented=value.get('frameReady') is not False
        backlog=type(queued_bytes) in (int,float) and queued_bytes>=self.BACKLOG_BYTES
        self.slow=self.slow+1 if rtt>450 else 0
        if presented and lag>700:return self.cut(now,.65,'stream_lag')
        if backlog:return self.cut(now,.65,'send_backlog')
        if self.slow:
            self.healthy_since=None
            near_budget=type(measured_bps) not in (int,float) or measured_bps>=self.bps*.6
            if self.slow>=2 and near_budget:return self.cut(now,.85,'slow_link')
            return None
        if presented and rtt<250 and lag<250:
            if self.healthy_since is None:self.healthy_since=now
            fast=self.bps<self.recover_to
            if self.bps<self.CEILING and now-self.healthy_since>=(6 if fast else 12):
                step=max(150000,int(self.bps*.2)) if fast else 150000
                self.bps=min(self.CEILING,self.bps+step);self.healthy_since=now-(2 if fast else 0)
                self.reason='recovering' if fast else 'probing';return self.reason
        else:self.healthy_since=None
        return None

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
