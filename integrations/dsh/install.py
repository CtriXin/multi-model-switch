#!/usr/bin/env python3
"""Install a private pinned distribution without changing MMS or shell config."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from config import DSH_VERSION, REPO, private_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--mms-root',type=Path,required=True)
    p.add_argument('--node',type=Path,required=True)
    p.add_argument('--runtime-from',type=Path)
    p.add_argument('--port',type=int,default=3091)
    args=p.parse_args();root=args.destination.expanduser().resolve();here=Path(__file__).resolve().parent
    protected = [(Path.home()/'.config'/name).resolve() for name in ('mms','mms-next')] + [args.mms_root.expanduser().resolve()]
    if any(root == q or q in root.parents for q in protected):p.error('Installation must be outside protected MMS config')
    if root.exists():p.error('Destination already exists; use a new installation directory to preserve the previous one')
    version=subprocess.check_output([str(args.node),'-p','process.versions.node'],text=True).strip()
    if tuple(map(int,version.split('.')[:2]))<(24,2):p.error('Node >=24.2 required')
    root.mkdir(parents=True,mode=0o700)
    source=root/'source'
    for relative in ['mms_consumer_bundle.py','mms_capability_resolver.py','mms_provider_profiles.py','mms_state_io.py','config/provider-profiles.json','apps/mms-web/src/recipe-core.ts']:
        dest=source/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(REPO/relative,dest)
    shutil.copytree(here,source/'integrations/dsh',ignore=shutil.ignore_patterns('__pycache__','node_modules','.pytest_cache'))
    runtime=root/'runtime'
    if args.runtime_from:
        original=args.runtime_from.resolve()
        installed=json.loads((original/'node_modules/@deepseek-ai/dsh/package.json').read_text())
        if installed['version']!=DSH_VERSION:p.error('Existing runtime is not the pinned DSH version')
        if json.loads((original/'package-lock.json').read_text())!=json.loads((here/'package-lock.json').read_text()):p.error('Runtime dependency lock differs')
        shutil.copytree(original,runtime,symlinks=True,ignore=shutil.ignore_patterns('*.tgz','mms-plugin'))
    else:
        runtime.mkdir()
        for name in ['package.json','package-lock.json']:shutil.copy2(here/name,runtime/name)
        npm=args.node.parent/'npm'
        subprocess.run([str(args.node),str(npm.resolve()),'ci','--ignore-scripts','--no-audit','--no-fund'],cwd=runtime,check=True)
    private_json(root/'installation.json',{'schema':'mms.dsh.installation.v1','dsh_version':DSH_VERSION,
        'python':sys.executable,'node':str(args.node.resolve()),'runtime':str(runtime),'instance':str(root/'instance'),
        'mms_root':str(args.mms_root.expanduser().resolve()),'workspace':str(root/'workspace'),'model':'deepseek-v4-flash','port':args.port})
    import shlex
    launcher=root/'MMS DSH.command'
    launcher.write_text('#!/bin/sh\nexec '+shlex.join([sys.executable,str(source/'integrations/dsh/service.py'),'--installation',str(root)])+' "$@"\n')
    launcher.chmod(0o700)
    print(str(launcher))

if __name__=='__main__':main()
