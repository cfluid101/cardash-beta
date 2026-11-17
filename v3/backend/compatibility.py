"""Bounded, read-only diagnostics; collecting these never starts a session."""
import asyncio
import ctypes
import json
import os
import uuid
from transport import notification_state

PREFIX = 'com.cfluid.cardash.v3.inventory.v1'
FRAMEWORKS = ('aptransport', 'mediaexperience', 'airplaysender')


def media_process_alive(pid):
    os.kill(pid, 0)
    library = ctypes.CDLL('/usr/lib/libproc.dylib')
    function = library.proc_pidpath
    function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    function.restype = ctypes.c_int
    path = ctypes.create_string_buffer(4096)
    if function(pid, path, len(path)) <= 0:
        raise OSError('Cannot verify inventory publisher process')
    if path.value != b'/usr/sbin/mediaserverd':
        raise ValueError('Inventory publisher is not the current media service')


def inventory_status(probe=None, alive=None):
    read = probe or notification_state
    result = {'event': 'native_media_inventory', 'schema_version': 1, 'complete': False}
    def get(field):
        return read((PREFIX + '.' + field).encode())
    def cpu(value):
        return {'cpuType': value >> 32, 'cpuSubtype': value & 0xffffffff}
    try:
        before = get('snapshot')
        failure_before = get('failure')
        if failure_before:
            failure_pid = failure_before >> 32
            failure_info = {'pid': failure_pid, 'phase': (failure_before >> 24) & 255,
                            'channel': (failure_before >> 16) & 255, 'notifyStatus': failure_before & 0xffff,
                            'publisherVerified': False}
            result['publicationFailure'] = failure_info
            if failure_pid > 1:
                try:
                    (alive or media_process_alive)(failure_pid)
                    failure_info['publisherVerified'] = True
                except (OSError, ValueError, AttributeError) as error:
                    failure_info['publisherError'] = str(error)
        pid, sequence = before >> 32, before & 0xffffffff
        result.update(pid=pid, sequence=sequence)
        if pid <= 1 or not sequence:
            raise ValueError('No inventory publication; adapter may not have loaded or notification access may have failed')
        if sequence & 1:
            raise ValueError('Inventory publication is incomplete')
        (alive or media_process_alive)(pid)
        adapter = cpu(get('cpu')); status = get('status')
        adapter.update(constructorEntered=bool(status & 1), initialScanComplete=bool(status & 2),
                       headerParsed=bool(status & 4), parseError=status >> 32)
        frameworks = {}
        for name in FRAMEWORKS:
            state = get(name + '.state'); value = cpu(get(name + '.cpu'))
            first, last = get(name + '.uuid0'), get(name + '.uuid1')
            code = state & 0xffffffff
            value.update(state={0: 'not_observed', 1: 'observed', 2: 'invalid', 3: 'ambiguous'}.get(code, 'unknown'),
                         stateCode=code, parseError=state >> 32)
            if code == 1 and not value['parseError']:
                value['uuid'] = str(uuid.UUID(int=(first << 64) | last)).upper()
            frameworks[name] = value
        after = get('snapshot'); failure = get('failure')
        if before != after or failure_before != failure:
            raise ValueError('Inventory changed while reading; export again')
        if failure >> 32 == pid:
            raise ValueError('Native inventory notification publication failed')
        result.update(adapter=adapter, frameworks=frameworks)
        if status & 7 != 7 or status >> 32:
            raise ValueError('Adapter inventory initialization incomplete')
        result.update(complete=True, error='')
    except (OSError, ValueError, AttributeError) as error:
        result['error'] = str(error)
    return result


async def inspect_session_helper(helper, timeout=10, limit=64 * 1024):
    """Run only the inspection entry point, drain bounded pipes, always reap."""
    result = {'event': 'native_session_inspection', 'schema_version': 1,
              'read_only': True, 'session_requested': False, 'complete': False}
    process = None
    tasks = []
    async def bounded_read(stream):
        chunks = []; size = 0
        while True:
            chunk = await stream.read(min(4096, limit + 1 - size))
            if not chunk: return b''.join(chunks)
            size += len(chunk)
            if size > limit: raise ValueError('Inspection output exceeded limit')
            chunks.append(chunk)
    try:
        process = await asyncio.create_subprocess_exec(str(helper), '--inspect',
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        tasks = [asyncio.create_task(bounded_read(process.stdout)),
                 asyncio.create_task(bounded_read(process.stderr)), asyncio.create_task(process.wait())]
        stdout, stderr, code = await asyncio.wait_for(asyncio.gather(*tasks), timeout)
        result['returncode'] = code
        if stderr: result['stderr'] = stderr.decode(errors='replace')[-2048:]
        records = []
        for line in stdout.splitlines():
            try: record = json.loads(line)
            except (ValueError, UnicodeDecodeError): continue
            if isinstance(record, dict) and record.get('event') == 'native_inspection': records.append(record)
        if len(records) != 1: raise ValueError('Expected one native_inspection record')
        record = records[0]
        if (record.get('schema_version') != 1 or record.get('inspection_kind') != 'carkit'
                or record.get('read_only') is not True or record.get('session_requested') is not False):
            raise ValueError('Invalid inspection schema or mode')
        result['inspection'] = record
        if code: raise ValueError('Inspection helper exited with status ' + str(code))
        if record.get('complete') is not True: raise ValueError('Native inspection did not complete')
        result.update(complete=True, error='')
    except asyncio.TimeoutError:
        result['error'] = 'Inspection helper timed out'
    except (OSError, ValueError) as error:
        result['error'] = str(error)
    finally:
        if process and process.returncode is None:
            try: process.kill()
            except ProcessLookupError: pass
        for task in tasks:
            if not task.done(): task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        if process: await process.wait()
    return result
