# SPDX-License-Identifier: GPL-3.0-only
"""Phone-local Tesla address lifecycle; no DNS/default-route changes."""
import ctypes
import os
from pathlib import Path

TESLA_ADDRESS = '100.99.10.2'


class TeslaNetwork:
    def __init__(self, port, probe=None):
        self.port = port
        self._probe = probe or self._native_probe
        self._library = None
        self.status = dict(address=TESLA_ADDRESS, url=None, ready=False,
                           interface='', added=False, error='Tesla address not checked yet')

    def _native_probe(self):
        if self._library is None:
            library = ctypes.CDLL(str(Path(__file__).with_name('libcardashnetwork.dylib')))
            library.cd_network_ensure.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                                  ctypes.POINTER(ctypes.c_int)]
            library.cd_network_ensure.restype = ctypes.c_int
            self._library = library
        interface = ctypes.create_string_buffer(32)
        added = ctypes.c_int()
        error = self._library.cd_network_ensure(interface, len(interface), ctypes.byref(added))
        return error, interface.value.decode('ascii'), bool(added.value)

    def refresh(self):
        try:
            error, interface, added = self._probe()
            ready = error == 0 and interface == 'lo0'
            message = '' if ready else (os.strerror(error) if error else 'Tesla address readback failed')
        except Exception as error:
            ready, interface, added, message = False, '', False, str(error)[:400]
        self.status = dict(address=TESLA_ADDRESS,
                           url=f'http://{TESLA_ADDRESS}:{self.port}/' if ready else None,
                           ready=ready, interface=interface, added=added, error=message)
        return self.status


def allowed_peer(address, network):
    # CGNAT is neither private nor globally routable in Python's ipaddress.
    # Permit the phone's own confirmed alias, without opening the CGNAT range.
    import ipaddress
    ip = ipaddress.ip_address(address)
    return ip.is_private or (network.status['ready'] and address == TESLA_ADDRESS)
