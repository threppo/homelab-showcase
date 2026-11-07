#!/usr/bin/env python3
from pathlib import Path
import ast, json, os, shutil, subprocess, tempfile
# Showcase-only runner: execute selected reviewed fixtures in a temporary copy.
# Never invoke the backup entrypoint, installer, remote restore or service tools.
export=Path(__file__).resolve().parent; report=[]
required=('bash','python3','node','sqlite3','rsync','jq','timeout','gzip','sed','awk','cmp','sha256sum')
missing=[name for name in required if not shutil.which(name)]
if missing:
    raise SystemExit('Missing local dependencies: '+', '.join(missing))
import yaml

with tempfile.TemporaryDirectory(prefix='homelab-source-review-') as directory:
 work=Path(directory)/'repository'; shutil.copytree(export/'repository',work)
 guard=Path(directory)/'guard'; guard.mkdir()
 for name in ('docker','curl','ssh','restic','systemctl','sudo'):
  file=guard/name; file.write_text('#!/bin/sh\necho "BLOCKED: operational tool unavailable in showcase validation" >&2\nexit 97\n'); file.chmod(0o700)
 env={'PATH':str(guard)+':/usr/bin:/bin','HOME':directory,'TMPDIR':directory,
      'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
 # Pure syntax checks: never execute operational scripts.
 shells=list(work.rglob('*.sh'))+[work/'scripts/audit/homelab-storage-report']
 for p in shells:
  result=subprocess.run(['bash','-n',str(p)],env=env,capture_output=True,text=True)
  if result.returncode: raise RuntimeError(str(p.relative_to(work))+result.stderr)
 report.append({'check':'shell syntax','files':len(shells),'result':'PASS'})
 py=list(work.rglob('*.py'))
 for p in py: ast.parse(p.read_text())
 report.append({'check':'Python AST','files':len(py),'result':'PASS'})
 for p in list(work.rglob('*.yml'))+list(work.rglob('*.yaml')):
  yaml.safe_load(p.read_text())
 for p in work.rglob('*.json'): json.loads(p.read_text())
 report.append({'check':'YAML/JSON parsing','result':'PASS'})
 # Selected original fixture suites only. Skip real Compose even for config parsing.
 runner='''import importlib.util,sys,unittest
from pathlib import Path
p=Path(sys.argv[1]); spec=importlib.util.spec_from_file_location("fixture_suite",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
if hasattr(m,"RecoveryTests"):
 name="test_compose_merges_bookorbit_override_pins_and_bootstrap"
 setattr(m.RecoveryTests,name,unittest.skip("Real Docker/Compose intentionally excluded")(getattr(m.RecoveryTests,name)))
r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(m))
print("RESULT",r.testsRun,"SKIPPED",len(r.skipped))
sys.exit(not r.wasSuccessful())
'''
 suites=['scripts/backup/test-dump-timeouts.py','scripts/backup/test-postersplus-capture.py',
         'scripts/recovery/test-recovery.py','scripts/recovery/test-immich-motion.py',
         'scripts/homepage/test-config.py']
 for suite in suites:
  result=subprocess.run(['python3','-c',runner,suite],cwd=work,env=env,capture_output=True,text=True,timeout=90)
  report.append({'check':suite,'result':'PASS' if result.returncode==0 else 'FAIL','output':result.stdout+result.stderr})
  print(report[-1]['result']+': '+report[-1]['check'])
  if result.returncode:
   print(result.stdout+result.stderr); raise SystemExit(result.returncode)
 for command in (['bash','scripts/backup/test-bookorbit-dump.sh'],['node','scripts/homepage/test-lol-schedule.cjs']):
  result=subprocess.run(command,cwd=work,env=env,capture_output=True,text=True,timeout=30)
  report.append({'check':' '.join(command),'result':'PASS' if result.returncode==0 else 'FAIL','output':result.stdout+result.stderr})
  print(report[-1]['result']+': '+report[-1]['check'])
  if result.returncode:
   print(result.stdout+result.stderr); raise SystemExit(result.returncode)
for item in report[:3]: print(item['result']+': '+item['check'])
print('PASS: source snapshot syntax and selected original fixture suites')
