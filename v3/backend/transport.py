"""Read the exact-build adapter's status; never infer readiness from a package version."""
import ctypes
import os


class MachClock:
    """Boot-relative clock shared with native code, including Python 3.9.

    Older Darwin Python versions subtract a per-process origin from monotonic().
    Its reported implementation name alone does not imply a shared epoch.
    """
    def __init__(self,library=None):
        library=library or ctypes.CDLL(None)
        self.ticks=library.mach_absolute_time;self.ticks.restype=ctypes.c_uint64
        ratio=(ctypes.c_uint32*2)()
        code=library.mach_timebase_info(ctypes.byref(ratio))
        if code or not ratio[1]:raise OSError('Mach audio lease clock unavailable')
        self.numer,self.denom=ratio[0],ratio[1]
    def __call__(self):return self.ticks()*self.numer/self.denom/1_000_000_000


def notification_state(name=b'com.cfluid.cardash.v3.loopback.ready'):
    library=ctypes.CDLL(None)
    token=ctypes.c_int();value=ctypes.c_uint64()
    code=library.notify_register_check(name,ctypes.byref(token))
    if code:raise OSError('readiness registration failed: '+str(code))
    try:
        code=library.notify_get_state(token.value,ctypes.byref(value))
        if code:raise OSError('readiness read failed: '+str(code))
        return value.value
    finally:library.notify_cancel(token.value)


class AudioLease:
    """Short-lived, PID-bound request; the native adapter restores on expiry."""
    def __init__(self,library=None,clock=None,pid=None):
        self.library=library;self.clock=clock;self.pid=os.getpid() if pid is None else pid;self.tokens={}
    def write(self,name,value):
        if self.library is None:self.library=ctypes.CDLL(None)
        if name not in self.tokens:
            token=ctypes.c_int()
            code=self.library.notify_register_check(name,ctypes.byref(token))
            if code:raise OSError('Audio route lease registration failed: '+str(code))
            self.tokens[name]=token.value
        code=self.library.notify_set_state(self.tokens[name],ctypes.c_uint64(value))
        if code:raise OSError('Audio route lease write failed: '+str(code))
    def refresh(self,phone):
        if not phone:self.clear();return
        if self.clock is None:self.clock=MachClock()
        self.write(b'com.cfluid.cardash.v3.audio.lease',int(self.clock()*1000))
        self.write(b'com.cfluid.cardash.v3.audio.request',(self.pid<<8)|1)
    def clear(self):
        if not self.tokens:return
        self.write(b'com.cfluid.cardash.v3.audio.request',0)
        self.write(b'com.cfluid.cardash.v3.audio.lease',0)


def audio_route_status(probe=None,alive=None,state_probe=None):
    result={'ready':False}
    try:
        value=(probe or (lambda:notification_state(b'com.cfluid.cardash.v3.audio.ready')))()
        pid,code=value>>8,value&255
        result.update(pid=pid,code=code)
        if pid<=1 or code!=1:raise ValueError('audio routing adapter unavailable (status '+str(code)+'); reinstall this beta or select Browser audio')
        (alive or (lambda pid:os.kill(pid,0)))(pid)
        try:
            state=(state_probe or (lambda:notification_state(b'com.cfluid.cardash.v3.audio.state')))()
            bits=state&255 if state>>16==pid else 0
        except (OSError,AttributeError):bits=0
        result.update(ready=True,error='',deviceOutputActive=bool(bits&4),leaseValid=bool(bits&8),ownHost=bool(bits&2))
    except (OSError,ValueError,AttributeError) as error:result['error']=str(error)
    return result


TRANSPORT_REASONS = {
    0: 'transport adapter ready',
    1: 'transport adapter is loading',
    2: 'unsupported APTransport firmware UUID or CPU',
    3: 'the 20A357 profile requires the arm64e adapter slice',
    4: 'native hook provider is unavailable',
    5: 'CMBaseObjectGetDerivedStorage is unavailable',
    6: 'transport entry bounds or executable mapping mismatch',
    7: 'transport entry instruction fingerprint mismatch',
    8: 'transport update hook failed',
    9: 'transport disconnect hook failed',
    10: 'live transport state mapping or type checks failed; no loopback writes made',
}


def transport_status(state=None, alive=None, probe=None, reason_probe=None):
    def running(pid):
        os.kill(pid,0)
    result={'ready':False}
    read=probe or notification_state
    try:
        value=read()
        pid,code=value>>8,value&255
        result.update(pid=pid,code=code)
        if pid<=1:raise ValueError('adapter not loaded; reinstall this beta to reload the media service')
        (alive or running)(pid)
        # Optional, PID-bound diagnostic state. Old adapters have no sideband;
        # absent, stale or unreadable details must not change the readiness ABI.
        try:
            detail=(reason_probe or (lambda:notification_state(b'com.cfluid.cardash.v3.loopback.ready_reason')))()
            detail_pid,detail_code,reason=detail>>32,(detail>>16)&0xffff,detail&0xffff
            if (detail_pid==pid and detail_code==code and code in (1,2) and
                    ((code==1)==(reason==0)) and read()==value):
                result['reasonCode']=reason
                if reason in TRANSPORT_REASONS:result['reason']=TRANSPORT_REASONS[reason]
        except (OSError,ValueError,AttributeError):pass
        if code!=1:
            detail=result.get('reason')
            raise ValueError(('adapter unavailable: '+detail+'; export diagnostics') if detail else
                             'adapter failed its exact-firmware or hook-provider check; export diagnostics')
        result.update(ready=True,error='')
    except (OSError,ValueError,AttributeError) as error:
        result['error']='USB-free transport is unavailable: '+str(error)
    return result


def startup_failure(active, frames, started, now, native_error=''):
    if not active:
        return ''
    if native_error:
        return 'iOS rejected the CarPlay request: ' + native_error
    if not frames and now - started >= 45:
        return 'iOS did not start native video within 45 seconds. Stop any other CarPlay connection, unlock once, and retry; export diagnostics if it persists.'
    return ''
