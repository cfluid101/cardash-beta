# SPDX-License-Identifier: GPL-3.0-only
"""Set and verify a bounded budget for this process, never another process.

The Dopamine launchd proxy ignores the job's JetsamProperties on the tested
iOS 16.6 build. XNU 8796's memorystatus API uses these four 32-bit fields.
"""
import ctypes
import os
import sys

def configure(limit=128):
    if sys.platform != 'darwin' or os.uname().machine != 'iPhone10,2':
        raise RuntimeError('V3 memory policy requires the supported iPhone 8 Plus')
    if os.getuid() != 0:
        raise RuntimeError('V3 service must run as root')
    libc=ctypes.CDLL(None,use_errno=True)
    control=libc.memorystatus_control
    control.argtypes=[ctypes.c_uint32,ctypes.c_int32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_size_t]
    control.restype=ctypes.c_int
    # MEMORYSTATUS_MEMLIMIT_ATTR_FATAL=1; both foreground and background bounded.
    requested=(ctypes.c_int32*4)(limit,1,limit,1)
    for command,values in [(7,requested),(8,(ctypes.c_int32*4)())]:
        if control(command,os.getpid(),0,ctypes.byref(values),ctypes.sizeof(values)):
            raise OSError(ctypes.get_errno(),'Cannot configure V3 process memory budget')
    if list(values)!=list(requested):
        raise RuntimeError('V3 process memory budget did not take effect')
    return {'activeMB':values[0],'inactiveMB':values[2],'verified':True}
