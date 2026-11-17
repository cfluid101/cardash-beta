"""Bounded, read-only diagnostics; collecting these never starts a session."""
import asyncio
import ctypes
import json
import os
import uuid
from transport import notification_state

PREFIX = 'com.cfluid.cardash.v3.inventory.v1'
FRAMEWORKS = ('aptransport', 'mediaexperience', 'airplaysender')


def diagnostic_fields(value, names):
    """Keep bounded facts only; never copy arbitrary status or credential objects."""
    if not isinstance(value, dict): return {}
    result = {}
    for name in names:
        item = value.get(name)
        if isinstance(item, str): result[name] = item[:1024]
        elif type(item) in (bool, int) and abs(item) <= 2**64: result[name] = item
    return result


def compatibility_summary(inventory, inspection, status):
    """Describe independent observed checks. This record never authorizes a hook."""
    inventory = inventory if isinstance(inventory, dict) else {}
    inspection = inspection if isinstance(inspection, dict) else {}
    status = status if isinstance(status, dict) else {}
    components, issues = {}, []
    export = 'Export diagnostic report after this attempt, including any matching crash report.'
    def issue(component, code, detail, optional=False):
        issues.append({'component': component, 'code': code,
                       'severity': 'optional' if optional else 'blocking',
                       'detail': str(detail or code)[:1024], 'next_step': export})
    identities = inventory.get('frameworks', {})
    if not isinstance(identities, dict): identities = {}
    inventory_ok = inventory.get('complete') is True and type(inventory.get('pid')) is int and inventory['pid'] > 1
    media_codes = {
        'transport': {2: 'identity_unsupported', 3: 'architecture_slice_mismatch',
                      4: 'hook_provider_unavailable', 5: 'required_symbol_missing',
                      6: 'entry_mapping_mismatch', 7: 'instruction_mismatch',
                      8: 'update_hook_failed', 9: 'disconnect_hook_failed',
                      10: 'live_layout_mismatch', 11: 'lifecycle_unsupported'},
        'video': {1: 'entry_address_overflow', 2: 'hook_provider_unavailable',
                  3: 'required_symbol_missing', 4: 'entry_mapping_mismatch',
                  5: 'instruction_mismatch', 6: 'property_key_mismatch',
                  7: 'copy_property_contract_mismatch', 8: 'hook_failed',
                  9: 'identity_unsupported', 10: 'architecture_slice_mismatch'},
        'audio': {2: 'initialization_incomplete', 3: 'identity_unsupported',
                  4: 'text_segment_mismatch', 5: 'data_segment_mismatch',
                  6: 'hook_provider_unavailable', 7: 'setter_mapping_mismatch',
                  8: 'flag_mapping_mismatch', 9: 'instruction_mismatch',
                  10: 'flag_value_invalid', 11: 'hook_failed'},
    }
    unverified = False
    for name, status_key, image in (('transport', 'transport', 'aptransport'),
                                     ('video', 'videoBudget', 'airplaysender'),
                                     ('audio', 'audioRouting', 'mediaexperience')):
        state = diagnostic_fields(status.get(status_key),
            ('ready', 'pid', 'code', 'reasonCode', 'reason', 'error', 'advice'))
        identity = diagnostic_fields(identities.get(image),
            ('state', 'stateCode', 'parseError', 'uuid', 'cpuType', 'cpuSubtype'))
        verified = inventory_ok and state.get('pid') == inventory['pid'] and identity.get('state') == 'observed'
        state['reported_ready'] = state.get('ready') is True
        state['ready'] = state['reported_ready'] and verified
        state['identity'] = identity
        state['publisher_verified'] = verified
        components[name] = state
        optional = name == 'audio' and status.get('audioOutput') == 'browser'
        if not state['reported_ready']:
            code = media_codes.get(name, {}).get(state.get('reasonCode'), 'unavailable')
            if state.get('pid', 0) <= 1: code = 'not_loaded'
            issue(name, name + '_' + code, state.get('error') or state.get('reason'), optional)
        elif not verified and not optional:
            unverified = True
    if not inventory_ok or unverified:
        issue('injection', 'media_inventory_unverified',
              inventory.get('error') or 'Readiness and framework inventory do not identify the same live media process.')
    raw_inspection = inspection.get('inspection', {})
    if not isinstance(raw_inspection, dict): raw_inspection = {}
    profile = diagnostic_fields(raw_inspection.get('host_profile'),
        ('selected_profile', 'profile_matched', 'request_family', 'host_schema',
         'diagnostic_code', 'evidence_level', 'device_validation_required', 'error', 'reason'))
    profile['ready'] = inspection.get('complete') is True and profile.get('profile_matched') is True
    profile['framework'] = diagnostic_fields(raw_inspection.get('framework'),
        ('path', 'loaded', 'image_uuid', 'load_error'))
    components['session'] = profile
    if inspection.get('complete') is not True:
        profile['error'] = str(inspection.get('error') or 'Inspection incomplete')[:1024]
        issue('session', 'session_inspection_unavailable', profile['error'])
    elif not profile['ready']:
        issue('session', profile.get('diagnostic_code') or 'session_contract_unsupported',
              profile.get('error') or profile.get('reason'))
    if status.get('error'):
        issue('runtime', 'native_session_or_media_error', status['error'])
    native = diagnostic_fields(status.get('native'), ('present', 'authenticated', 'activated'))
    frames = status.get('nativeFrames', 0)
    observed = (status.get('active') is True and type(frames) is int and frames > 0 and
                native.get('present') is True and native.get('authenticated') is True)
    blocked = any(item['severity'] == 'blocking' for item in issues)
    return {'event': 'compatibility_summary', 'schema_version': 1, 'diagnostic_only': True,
            'version': str(status.get('version', ''))[:128], 'components': components,
            'issues': issues, 'verdict': 'blocked' if blocked else 'ready_for_device_trial',
            'session_observed': observed, 'native_observation': native,
            'evidence_limit': 'Framework checks and observed session state do not certify all features or other firmware.'}


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
