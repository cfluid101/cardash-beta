import json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class EmitTests(unittest.TestCase):
    def test_parallel_callbacks_preserve_complete_json_lines(self):
        binary=ROOT/'build/host/emit-tests'
        subprocess.run(['xcrun','clang++','-x','objective-c++','-std=c++17','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-I',str(ROOT/'src'),str(ROOT/'tests/EmitTests.mm'),str(ROOT/'src/Common.m'),'-framework','Foundation','-o',str(binary)],check=True,capture_output=True)
        result=subprocess.run([str(binary)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=True)
        rows=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(rows),192)
        self.assertEqual({(r['worker'],r['sequence']) for r in rows},{(w,s) for w in range(16) for s in range(12)})
        for row in rows:
            self.assertEqual(row['event'],'parallel_emit');self.assertEqual(row['payload'],'x'*65536)

if __name__=='__main__':unittest.main()
