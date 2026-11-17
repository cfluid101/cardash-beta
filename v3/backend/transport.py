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


# Audio's original readiness byte already distinguishes the native guard. Keep
# that ABI; decoding it also gives useful diagnostics for an older adapter.
AUDIO_READY_REASONS = {
    0: 'ready',
    2: 'initialization_incomplete',
    3: 'unsupported_image_identity_or_cpu',
    4: 'text_segment_mismatch',
    5: 'data_segment_mismatch',
    6: 'hook_provider_unavailable',
    7: 'setter_mapping_mismatch',
    8: 'flag_mapping_mismatch',
    9: 'setter_prologue_mismatch',
    10: 'flag_value_invalid',
    11: 'hook_installation_failed',
}


def audio_route_status(probe=None,alive=None,state_probe=None):
    result={'ready':False}
    try:
        value=(probe or (lambda:notification_state(b'com.cfluid.cardash.v3.audio.ready')))()
        pid,code=value>>8,value&255
        result.update(pid=pid,code=code)
        if pid<=1:
            result.update(reason='adapter_not_loaded',
                          advice='Restart the phone (userspace reboot) with tweak injection enabled, then Export Diagnostics if the audio adapter remains unavailable.')
            raise ValueError('audio routing adapter has not loaded')
        try:
            (alive or (lambda pid:os.kill(pid,0)))(pid)
        except OSError:
            result.update(reason='publisher_not_running',
                          advice='Restart the phone (userspace reboot), then Export Diagnostics if the audio adapter remains unavailable.')
            raise ValueError('audio adapter status belongs to a media process that is no longer available')
        reason_code=0 if code==1 else code
        # Invalid status zero must not borrow the successful reason.
        reason=AUDIO_READY_REASONS.get(reason_code,'unknown_readiness_code') if code else 'unknown_readiness_code'
        result.update(reasonCode=reason_code,reason=reason)
        if code!=1:
            if code==3:
                advice=('This MediaExperience framework has no verified audio profile in this beta; reinstalling will not add one. '
                        'Export Diagnostics so its identity can be checked. Select Browser audio to try without the device-output adapter.')
            elif code==6:
                advice=('Enable a Substrate-compatible hook provider such as ElleKit, restart the phone (userspace reboot), '
                        'and Export Diagnostics if it remains unavailable.')
            else:
                advice=('Export Diagnostics to capture the exact MediaExperience identity and failed guard. '
                        'Select Browser audio to try without the device-output adapter.')
            result['advice']=advice
            raise ValueError('audio routing adapter unavailable: '+reason+' (status '+str(code)+'); '+advice)
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
    3: 'loaded transport adapter slice does not match the framework architecture',
    4: 'native hook provider is unavailable',
    5: 'CMBaseObjectGetDerivedStorage is unavailable',
    6: 'transport entry bounds or executable mapping mismatch',
    7: 'transport entry instruction fingerprint mismatch',
    8: 'transport update hook failed',
    9: 'transport disconnect hook failed',
    10: 'live transport state mapping or type checks failed; no loopback writes made',
    11: 'recognised early iOS 15 transport lifecycle is not implemented; no hooks installed',
}


NOT_LOADED_ADVICE = ('The media service has not loaded the CarDash adapter. Restart the phone '
                     '(userspace reboot) with tweak injection enabled; reinstall this beta only if that does not help.')
# What the person holding the phone can do about each reason. Reinstalling does
# not change a framework identity, so it is not suggested where it cannot help.
TRANSPORT_ADVICE = {
    8: ('The update hook attempt failed. Session startup is blocked; export diagnostics and restart '
        'the media service with a userspace reboot before retrying. Hook rollback is not confirmed.'),
    9: ('The disconnect hook attempt failed after the update hook was installed. Session startup is blocked; '
        'export diagnostics and restart the media service with a userspace reboot before retrying.'),
    10: ('The adapter rejected the live state and forwarded this native callback without loopback writes. '
         'Export Diagnostics so the state/layout failure can be investigated.'),
    11: ('This firmware uses a different USB-disconnect ownership path that this beta cannot safely preserve. '
         'Export Diagnostics from CarDash V3; reinstalling does not add that missing adapter.'),
    2: ('This iOS build{build} is not supported by this beta yet; reinstalling will not change that. '
        'In the CarDash V3 app tap Export Diagnostics and send the file so a profile for this build can be added.'),
    3: 'Reinstall this beta so the matching arm64 or arm64e adapter slice is loaded, then restart the phone (userspace reboot).',
    4: ('No Substrate-compatible hooking library was found. Install ElleKit (or Substitute) from your '
        'package manager, then restart the phone (userspace reboot).'),
}
GENERIC_ADVICE = ('The adapter recognised this iOS build{build} but a safety check failed, so nothing was patched. '
                  'In the CarDash V3 app tap Export Diagnostics and send the file.')


def os_build(library=None):
    """Kernel build string such as 20G75; empty when it cannot be read."""
    try:
        library = library or ctypes.CDLL(None)
        size = ctypes.c_size_t(32)
        value = ctypes.create_string_buffer(32)
        if library.sysctlbyname(b'kern.osversion', value, ctypes.byref(size), None, ctypes.c_size_t(0)):
            return ''
        text = value.value.decode('ascii', 'replace')
        return text if text.isalnum() and len(text) <= 16 else ''
    except (OSError, AttributeError, ValueError):
        return ''


def transport_advice(reason=None, loaded=True, build=''):
    label = ' (' + build + ')' if build else ''
    if not loaded:
        return NOT_LOADED_ADVICE
    return TRANSPORT_ADVICE.get(reason, GENERIC_ADVICE).format(build=label)


def transport_status(state=None, alive=None, probe=None, reason_probe=None, build=None):
    def running(pid):
        os.kill(pid,0)
    result={'ready':False}
    read=probe or notification_state
    try:
        value=read()
        pid,code=value>>8,value&255
        result.update(pid=pid,code=code)
        if pid<=1:
            result['advice']=transport_advice(loaded=False)
            raise ValueError('adapter not loaded')
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
            result['build']=os_build() if build is None else build
            result['advice']=transport_advice(result.get('reasonCode'),build=result['build'])
            detail=result.get('reason')
            raise ValueError(('adapter unavailable: '+detail+'; export diagnostics') if detail else
                             'adapter failed its exact-firmware or hook-provider check; export diagnostics')
        result.update(ready=True,error='')
    except (OSError,ValueError,AttributeError) as error:
        result['error']='USB-free transport is unavailable: '+str(error)
        # One sentence a tester can act on, after the stable diagnostic text.
        if result.get('advice'):result['error']+='. '+result['advice']
    return result


def startup_failure(active, frames, started, now, native_error=''):
    if not active:
        return ''
    if native_error:
        return 'iOS rejected the CarPlay request: ' + native_error
    if not frames and now - started >= 45:
        return 'iOS did not start native video within 45 seconds. Stop any other CarPlay connection, unlock once, and retry; export diagnostics if it persists.'
    return ''
