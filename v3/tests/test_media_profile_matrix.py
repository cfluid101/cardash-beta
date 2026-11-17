"""Firmware-derived fixtures catch wrong entry/ABI/flag selection, independently of the tables."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name('fixtures') / 'media_profiles_beta9.json'


def bytes_c(hex_string):
    return '{' + ','.join('0x' + hex_string[i:i+2] for i in range(0, len(hex_string), 2)) + '}'


class MediaProfileMatrixTest(unittest.TestCase):
    def test_inspected_images_choose_exact_entry_and_audio_flag(self):
        chunks = []
        for sample in json.loads(FIXTURE.read_text())['samples']:
            v, a = sample['video'], sample['audio']
            chunks.append(f'''
 {{
 uint8_t vuuid[]={bytes_c(v['uuid'].replace('-', '').lower())};
 uint8_t auuid[]={bytes_c(a['uuid'].replace('-', '').lower())};
 const uint8_t videoEntry[]={bytes_c(v['entry16'])}, audioEntry[]={bytes_c(a['entry16'])};
 const auto *v=CDV3VideoBudgetFindProfile(vuuid,{v['cpu_type']},{v['cpu_subtype']});
 const auto *a=CDV3AudioProfiles::Find(auuid,{a['cpu_type']},{a['cpu_subtype']});
 assert(v && a && "Missing inspected media profile: {sample['sample']}");
 assert(v->abi==CDV3VideoBudgetABI::{v['abi']} && v->offset=={v['offset']});
 assert(!memcmp(v->prologue,videoEntry,16));
 assert(a->text=={a['text']}ULL && a->setter=={a['setter']}ULL && a->flag=={a['flag']}ULL);
 assert(!memcmp(a->prologue,audioEntry,16));
 assert(decodedAddress(*a)=={a['flag']}ULL);
 assert(!CDV3VideoBudgetFindProfile(vuuid,{v['cpu_type']},{v['cpu_subtype']}^0x80000002));
 assert(!CDV3AudioProfiles::Find(auuid,{a['cpu_type']},{a['cpu_subtype']}^0x80000002));
 assert(!CDV3VideoBudgetFindProfile(vuuid,7,{v['cpu_subtype']}));
 assert(!CDV3AudioProfiles::Find(auuid,7,{a['cpu_subtype']}));
 vuuid[15]^=1;auuid[15]^=1;
 assert(!CDV3VideoBudgetFindProfile(vuuid,{v['cpu_type']},{v['cpu_subtype']}));
 assert(!CDV3AudioProfiles::Find(auuid,{a['cpu_type']},{a['cpu_subtype']}));
 }}
''')
        source = r'''
#include "VideoBudgetProfiles.h"
#include "AudioRouteProfile.h"
#include <cassert>
#include <cstring>
static uint64_t decodedAddress(const CDV3AudioProfiles::Profile &p) {
 uint32_t code[4];memcpy(code,p.prologue,16);
 assert((code[0]&0x9f00001f)==0x90000008);
 int64_t pages=((code[0]>>29)&3)|(((code[0]>>5)&0x7ffff)<<2);
 if(pages&(1<<20))pages-=1<<21;
 assert((code[1]&0xffc003ff)==0x91000108);
 assert((code[2]&0xffc003ff)==0x39000100);
 assert(code[3]==0xd65f03c0);
 return (p.setter&~uint64_t(4095))+(pages*4096)+((code[1]>>10)&4095)+((code[2]>>10)&4095);
}
int main(){
''' + '\n'.join(chunks) + '\n}\n'
        with tempfile.TemporaryDirectory() as directory:
            source_path, binary = Path(directory)/'matrix.cc', Path(directory)/'matrix'
            source_path.write_text(source)
            subprocess.run(['xcrun', 'clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT/'v3/native'), str(source_path), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
