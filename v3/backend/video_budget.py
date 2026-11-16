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

    Beta 5 cut 35% whenever one heartbeat round trip exceeded 450 ms: 45 of 51
    cuts in the owner's first log had nothing waiting to be sent. Beta 6 cut on
    late pictures and unsent video instead, but cut the budget rather than the
    stream. On the November 15 drive the encoder was sending 1.3-1.6 Mbps under
    a 2.1-3.0 Mbps budget when the link congested, so a 35% budget cut changed
    nothing and the same congestion returned: 18 cuts in 20 minutes, each a
    visible stutter. A cut now starts from what is actually being sent, and the
    rate that congested is remembered before it is approached again.
    """
    CEILING=3000000;FLOOR=750000;BACKLOG_BYTES=192*1024;BACKLOG_FRAGMENTS=20;IDLE_BPS=100000
    def __init__(self):
        self.bps=self.CEILING;self.last=-float('inf');self.healthy_since=None
        self.cut_at=-float('inf');self.slow=0;self.reason=''
        # limit: the sending rate at the last congestion. While it is held the
        # budget stays under it; afterwards it is probed slowly. A probe that
        # fails soon after release doubles the next hold.
        self.limit=0;self.limit_at=-float('inf');self.hold=120;self.released_at=-float('inf')
    def cut(self,now,factor,reason,measured=None):
        # One reduction per congestion event: the encoder and the queued video
        # need a few seconds to reflect it before the same lag is counted again.
        self.healthy_since=None
        if now-self.cut_at<4 or self.bps<=self.FLOOR:return None
        base=self.bps
        if type(measured) in (int,float) and math.isfinite(measured) and self.FLOOR<=measured<base:base=int(measured)
        if self.released_at is not None:
            self.hold=min(600,self.hold*2) if self.limit and now-self.released_at<90 else 120
        self.limit=base;self.limit_at=now;self.released_at=None
        self.cut_at=now;self.slow=0;self.bps=max(self.FLOOR,int(base*factor));self.reason=reason
        return reason
    def feedback(self,value,now,queued_bytes=0,measured_bps=None,queued_fragments=0,settling=False):
        """Apply one browser report. Returns the reason when the budget changed."""
        if not isinstance(value,dict) or value.get('hidden') is True:return None
        rtt,lag=value.get('heartbeatRttMs'),value.get('streamLagMs')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (rtt,lag)):return None
        if now-self.last<1.5:return None
        self.last=now
        number=lambda v:type(v) in (int,float) and math.isfinite(v)
        presented=value.get('frameReady') is not False
        backlog=(number(queued_bytes) and queued_bytes>=self.BACKLOG_BYTES) or (number(queued_fragments) and queued_fragments>=self.BACKLOG_FRAGMENTS)
        # Lag is the newest native frame minus the last one shown. After a still
        # screen, or while a viewer waits for its keyframe, that difference is
        # the pause itself: two of beta 6's cuts were that, both in the first
        # seconds of a session.
        idle=number(measured_bps) and measured_bps<self.IDLE_BPS
        self.slow=self.slow+1 if rtt>450 else 0
        if presented and lag>700 and not idle and not settling:return self.cut(now,.8,'stream_lag',measured_bps)
        if backlog:return self.cut(now,.8,'send_backlog',measured_bps)
        if self.slow:
            self.healthy_since=None
            near_budget=not number(measured_bps) or measured_bps>=self.bps*.6
            if self.slow>=2 and near_budget:return self.cut(now,.9,'slow_link',measured_bps)
            return None
        if presented and rtt<250 and lag<250:
            if self.healthy_since is None:self.healthy_since=now
            holding=bool(self.limit) and now-self.limit_at<self.hold
            if self.limit and not holding and self.released_at is None:self.released_at=now
            if holding:
                allowed=max(self.FLOOR,int(self.limit*.9))
                if self.bps<allowed and now-self.healthy_since>=6:
                    self.bps=min(allowed,max(self.bps+50000,int(self.bps*1.1)));self.healthy_since=now-2
                    self.reason='recovering';return self.reason
            elif self.bps<self.CEILING and now-self.healthy_since>=12:
                self.bps=min(self.CEILING,self.bps+150000);self.healthy_since=now
                self.reason='probing';return self.reason
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
