"""Read the exact-build adapter's status; never infer readiness from a package version."""
import ctypes
import os


def notification_state():
    library=ctypes.CDLL(None)
    token=ctypes.c_int();value=ctypes.c_uint64()
    code=library.notify_register_check(b'com.cfluid.cardash.v3.loopback.ready',ctypes.byref(token))
    if code:raise OSError('readiness registration failed: '+str(code))
    try:
        code=library.notify_get_state(token.value,ctypes.byref(value))
        if code:raise OSError('readiness read failed: '+str(code))
        return value.value
    finally:library.notify_cancel(token.value)


def transport_status(state=None, alive=None, probe=None):
    def running(pid):
        os.kill(pid,0)
    try:
        value=(probe or notification_state)()
        pid,code=value>>8,value&255
        if pid<=1:raise ValueError('adapter not loaded; reinstall this beta to reload the media service')
        (alive or running)(pid)
        if code!=1:raise ValueError('adapter failed its exact-firmware or hook-provider check; export diagnostics')
        return {'ready':True,'pid':pid,'imageUUID':'BCC474F5-2745-3652-995F-A06F650F76FC','error':''}
    except (OSError,ValueError,AttributeError) as error:
        return {'ready':False,'error':'USB-free transport is unavailable: '+str(error)}


def startup_failure(active, frames, started, now, native_error=''):
    if not active:
        return ''
    if native_error:
        return 'iOS rejected the CarPlay request: ' + native_error
    if not frames and now - started >= 45:
        return 'iOS did not start native video within 45 seconds. Stop any other CarPlay connection, unlock once, and retry; export diagnostics if it persists.'
    return ''
