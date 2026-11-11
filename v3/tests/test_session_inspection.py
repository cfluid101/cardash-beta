from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class SessionInspectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='cardash-inspection-')
        cls.binary = Path(cls.tmp.name) / 'session-helper'
        sources = [ROOT / 'v3/native/SessionProbe.mm', ROOT / 'src/Common.m',
                   ROOT / 'src/NativeIdentity.mm', ROOT / 'src/HostPayload.mm']
        # Permit the pre-fix CLI to build, so the regression fails on behavior
        # (missing --inspect), rather than on a nonexistent source file.
        inspection = ROOT / 'v3/native/SessionInspection.mm'
        if inspection.exists():
            sources.append(inspection)
        cls.flags = ['xcrun', 'clang++', '-x', 'objective-c++', '-std=c++17',
                        '-fobjc-arc', '-fblocks', '-Wall', '-Wextra', '-Werror',
                        '-Wno-deprecated-declarations', '-I', str(ROOT / 'src'),
                        '-I', str(ROOT / 'v3/native')]
        subprocess.run([*cls.flags, *map(str, sources), '-framework', 'Foundation', '-o',
                        str(cls.binary)], check=True, capture_output=True)
        fixture = Path(cls.tmp.name) / 'Fixture.mm'
        fixture.write_text(r'''
#import <Foundation/Foundation.h>
#include <unistd.h>
@interface CARSessionRequestHost : NSObject
@end
@implementation CARSessionRequestHost
+ (void)initialize {_exit(91);}
- (id)initWithDisplayName:(id)n wiredIPv6Addresses:(id)w wirelessIPv6Addresses:(id)r port:(long long)p carplayWiFiUUID:(id)u deviceIdentifier:(id)i publicKey:(id)k sourceVersion:(id)v wiredCarPlaySimulator:(bool)s {_exit(92);}
@end
@interface CARSessionRequestClient : NSObject
@end
@implementation CARSessionRequestClient
+ (void)initialize {_exit(93);}
- (void)startSessionWithHost:(id)h completion:(void(^)(bool,NSError *))c {_exit(94);}
#ifdef MISMATCH
- (long long)cancelRequests {_exit(95);}
#else
- (void)cancelRequests {_exit(95);}
#endif
@end
@interface CARSessionStatus : NSObject
@end
@implementation CARSessionStatus
+ (void)initialize {_exit(96);}
- (id)currentSession {_exit(97);}
@end
''')
        cls.fixture = Path(cls.tmp.name) / 'Fixture.dylib'
        cls.mismatch_fixture = Path(cls.tmp.name) / 'Mismatch.dylib'
        for output, extra in ((cls.fixture, []), (cls.mismatch_fixture, ['-DMISMATCH'])):
            subprocess.run([*cls.flags, '-dynamiclib', *extra, str(fixture),
                            '-framework', 'Foundation', '-o', str(output)],
                           check=True, capture_output=True)
        driver = Path(cls.tmp.name) / 'Driver.mm'
        driver.write_text(r'''
#import "SessionInspection.h"
#import "Common.h"
int main(int argc,char **argv){@autoreleasepool{
    if(argc!=2)return 2;
    CDEmit(@"native_inspection",CDV3InspectCarKitAtPath(@(argv[1])));return 0;
}}
''')
        cls.driver = Path(cls.tmp.name) / 'inspection-driver'
        subprocess.run([*cls.flags, str(driver), str(inspection),
                        str(ROOT / 'src/Common.m'), str(ROOT / 'src/NativeIdentity.mm'),
                        '-framework', 'Foundation', '-o', str(cls.driver)],
                       check=True, capture_output=True)
        slow_loader = Path(cls.tmp.name) / 'SlowLoader.c'
        slow_loader.write_text(r'''
#include <dlfcn.h>
#include <string.h>
#include <unistd.h>
static void *slow_dlopen(const char *path,int mode){
    if(path&&!strcmp(path,"/System/Library/PrivateFrameworks/CarKit.framework/CarKit"))sleep(60);
    return dlopen(path,mode);
}
__attribute__((used,section("__DATA,__interpose"))) static struct {
    const void *replacement; const void *replacee;
} interpose={(const void *)slow_dlopen,(const void *)dlopen};
''')
        cls.slow_loader = Path(cls.tmp.name) / 'SlowLoader.dylib'
        subprocess.run(['xcrun', 'clang', '-Wall', '-Wextra', '-Werror', '-dynamiclib',
                        str(slow_loader), '-o', str(cls.slow_loader)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_inspect_emits_one_read_only_report_without_session_arguments(self):
        result = subprocess.run([str(self.binary), '--inspect'], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(records), 1)
        report = records[0]
        self.assertEqual(report['event'], 'native_inspection')
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(report['inspection_kind'], 'carkit')
        self.assertTrue(report['read_only'])
        self.assertFalse(report['session_requested'])
        self.assertTrue(report['complete'])
        self.assertLess(len(result.stdout.encode()), 32768)
        for field in ('machine', 'os_version', 'build', 'process_architecture'):
            self.assertIsInstance(report[field], str)
        self.assertIn('typed_completion_enabled', report['completion_identity'])
        self.assertEqual(len(report['methods']), 4)
        self.assertNotIn('request_started', result.stdout)
        self.assertNotIn('timing_sync', result.stdout)
        self.assertNotIn('cleanup', result.stdout)

    def test_normal_mode_still_rejects_incomplete_or_invalid_arguments(self):
        for args in ([], ['--unknown'], ['--inspect', 'extra'],
                     ['--inspect', 'extra', 'extra']):
            with self.subTest(args=args):
                result = subprocess.run([str(self.binary), *args], capture_output=True,
                                        text=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')

    def inspect_fixture(self, path):
        result = subprocess.run([str(self.driver), str(path)], capture_output=True,
                                text=True, timeout=10)
        # Fixture +initialize and every session operation abort. A zero exit
        # proves the inspector queried real metadata without invoking them.
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        return json.loads(result.stdout)

    def test_real_method_metadata_is_inspected_without_creating_session_objects(self):
        report = self.inspect_fixture(self.fixture)
        self.assertTrue(report['complete'])
        self.assertFalse(report['session_requested'])
        self.assertTrue(report['framework']['loaded'])
        self.assertEqual(report['framework']['image_path'], str(self.fixture.resolve()))
        self.assertRegex(report['framework']['image_uuid'], r'^[A-F0-9-]{36}$')
        self.assertFalse(report['normal_mode_method_checks_passed'])
        self.assertFalse(report['completion_identity']['typed_completion_enabled'])
        self.assertFalse(report['completion_block_abi_inferred_from_method_encoding'])
        for record in report['methods']:
            self.assertTrue(record['available'])
            self.assertTrue(record['matches_expected_types'], record)
            self.assertFalse(record['matches_normal_owner_checks'])
            self.assertEqual(record['implementation_image'], str(self.fixture.resolve()))
            self.assertEqual(record['implementation_uuid'], report['framework']['image_uuid'])
            self.assertFalse(record['arguments_truncated'])
        self.assertEqual(report['methods'][0]['argument_types'],
                         ['@', '@', '@', 'q', '@', '@', '@', '@', 'B'])
        self.assertEqual(report['methods'][1]['argument_types'], ['@', '@?'])
        self.assertEqual(report['methods'][2]['return_type'], 'v')
        self.assertEqual(report['methods'][3]['return_type'], '@')

    def test_method_abi_difference_is_reported_without_calling_it(self):
        report = self.inspect_fixture(self.mismatch_fixture)
        self.assertEqual(report['methods'][2]['return_type'], 'q')
        self.assertFalse(report['methods'][2]['matches_expected_types'])
        self.assertTrue(report['methods'][0]['matches_expected_types'])
        self.assertFalse(report['completion_identity']['typed_completion_enabled'])

    def test_missing_framework_is_reported_without_losing_identity_facts(self):
        report = self.inspect_fixture(Path(self.tmp.name) / 'Missing.dylib')
        self.assertTrue(report['complete'])
        self.assertFalse(report['framework']['loaded'])
        self.assertTrue(report['framework']['load_error'])
        self.assertLessEqual(len(report['framework']['load_error']), 1024)
        self.assertTrue(all(not record['available'] for record in report['methods']))
        self.assertIn('daemon_file', report['completion_identity'])
        self.assertFalse(report['completion_identity']['typed_completion_enabled'])

    def test_cli_alarm_terminates_a_stalled_framework_load(self):
        environment = dict(os.environ, DYLD_INSERT_LIBRARIES=str(self.slow_loader))
        result = subprocess.run([str(self.binary), '--inspect'], env=environment,
                                capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
