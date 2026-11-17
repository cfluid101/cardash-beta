from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class AudioProfilesTest(unittest.TestCase):
    def test_exact_identity_cpu_and_setter_machine_code(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'profiles.cc'
            binary = Path(directory) / 'profiles'
            source.write_text(r'''
#include "AudioRouteProfile.h"
#include <cassert>
#include <cstring>
using namespace CDV3AudioProfiles;
static uint64_t storedAddress(const Profile &p) {
 uint32_t code[4];memcpy(code,p.prologue,16);
 assert((code[0]&0x9f00001f)==0x90000008); // ADRP x8
 int64_t pages=((code[0]>>29)&3)|(((code[0]>>5)&0x7ffff)<<2);
 if(pages&(1<<20))pages-=1<<21;
 assert((code[1]&0xffc003ff)==0x91000108); // ADD x8,x8,#imm
 assert((code[2]&0xffc003ff)==0x39000100); // STRB w0,[x8,#imm]
 assert(code[3]==0xd65f03c0); // RET
 return (p.setter&~uint64_t(4095))+(pages*4096)+((code[1]>>10)&4095)+((code[2]>>10)&4095);
}
int main(){
 uint8_t oldID[]={0x17,0x90,0xdb,0xae,0x04,0xb6,0x32,0xb7,0xb5,0xe7,0xaa,0x39,0xe5,0x71,0xb2,0x08};
 uint8_t newID[]={0xf9,0x44,0x81,0x7f,0x4a,0x89,0x31,0xee,0xa4,0xf6,0x0d,0xa7,0x74,0x9d,0x2d,0xac};
 // Independently recorded iPhone14,2 / 19E258 firmware identity and setter.
 uint8_t ios15ID[]={0x57,0x8e,0x18,0x2e,0x81,0x0f,0x39,0xce,0xa0,0x68,0xc0,0x26,0xd4,0x28,0x81,0x22};
 const uint8_t ios15Setter[]={0xc8,0x39,0x1e,0xd0,0x08,0xe1,0x21,0x91,0x00,0x61,0x09,0x39,0xc0,0x03,0x5f,0xd6};
 const auto *old=Find(oldID,0x100000c,0);const auto *target=Find(newID,0x100000c,0x80000002);
 assert(old&&target&&old!=target);
 assert(old->text==0x1959c6000 && old->setter==0x195a6450c && old->flag==0x1dd3753e0);
 assert(target->text==0x196468000 && target->setter==0x196516c50 && target->flag==0x1da661cb8);
 assert(storedAddress(*old)==old->flag && storedAddress(*target)==target->flag);
 const auto *ios15=Find(ios15ID,0x100000c,0x80000002);
 assert(ios15 && "15.4.1 MediaExperience profile missing");
 assert(ios15!=old && ios15!=target);
 assert(ios15->text==0x19ae4f000 && ios15->setter==0x19aefc58c);
 assert(!memcmp(ios15->prologue,ios15Setter,sizeof(ios15Setter)));
 // Decode the selected instructions at their recorded PC: a wrong page,
 // immediate, or hardcoded flag must not silently select another route flag.
 assert(storedAddress(*ios15)==0x1d7636ad0 && ios15->flag==0x1d7636ad0);
 assert(!Find(ios15ID,0x100000c,0));assert(!Find(ios15ID,0x100000c,2));
 assert(!Find(ios15ID,7,0x80000002));
 ios15ID[15]^=1;assert(!Find(ios15ID,0x100000c,0x80000002));
 assert(!Find(newID,0x100000c,0));assert(!Find(oldID,0x100000c,0x80000002));
 assert(!Find(newID,7,0x80000002));assert(!Find(nullptr,0x100000c,0));
 newID[0]^=1;assert(!Find(newID,0x100000c,0x80000002));
}
''')
            subprocess.run(['xcrun', 'clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'v3/native'), str(source), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
