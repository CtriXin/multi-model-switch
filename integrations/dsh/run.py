#!/usr/bin/env python3
"""Launch the opt-in DSH profile with a verified MMS snapshot and private HOME."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from config import configure

HERE = Path(__file__).resolve().parent


def launch_env(instance, node):
    # Allowlist excludes inherited provider keys, OAuth paths, NODE_OPTIONS,
    # MMS real HOME aliases and user hooks. DSH uses its own credential store.
    env = {k: os.environ[k] for k in ('LANG', 'LC_ALL', 'TERM', 'TMPDIR') if k in os.environ}
    env.update({'PATH': str(node.parent) + ':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin',
        'HOME': str(instance / 'user-home'), 'XDG_CONFIG_HOME': str(instance / 'user-home/.config'),
        'XDG_DATA_HOME': str(instance / 'user-home/.local/share'), 'DSH_HOME': str(instance / 'home'),
        'DSH_TELEMETRY_DISABLED': '1', 'MMS_DSH_ROUTES': str(instance / 'routes.json'),
        'MMS_DSH_EVIDENCE': str(instance / 'transport.jsonl')})
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--instance', type=Path, required=True)
    parser.add_argument('--mms-root', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--model', default='deepseek-v4-flash')
    parser.add_argument('--port', type=int, default=3091)
    parser.add_argument('--configure-only', action='store_true')
    args = parser.parse_args()
    instance, root, workspace = args.instance.expanduser().resolve(), args.mms_root.expanduser().resolve(), args.workspace.expanduser().resolve()
    node, runtime = args.node.expanduser().resolve(), args.runtime.expanduser().resolve()
    protected = [(Path.home()/'.config'/name).resolve() for name in ('mms', 'mms-next')]
    if any(instance == p or p in instance.parents for p in [root, *protected]):
        parser.error('Instance must be outside the read-only MMS config roots')
    if any(p in workspace.parents or workspace == p for p in protected):
        parser.error('Do not use protected MMS config as an agent workspace')
    if not node.is_file():
        parser.error('Explicit Node executable missing')
    version = subprocess.check_output([str(node), '-p', 'process.versions.node'], text=True).strip()
    if tuple(map(int, version.split('.')[:2])) < (24, 2):
        parser.error('DSH requires Node >=24.2 for import.meta.main')
    cli = runtime / 'node_modules/@deepseek-ai/dsh/lib/bin.js'
    if not cli.is_file():
        parser.error('Install the pinned runtime first with npm ci')
    instance.mkdir(parents=True, exist_ok=True, mode=0o700)
    (instance/'user-home').mkdir(exist_ok=True, mode=0o700)
    workspace.mkdir(parents=True, exist_ok=True)
    plugin_dir = runtime / 'mms-plugin'
    plugin_dir.mkdir(exist_ok=True)
    shutil.copy2(HERE/'plugin.mjs', plugin_dir/'plugin.mjs')
    previous = None
    credential_file = instance/'home/.credentials.yaml'
    if credential_file.exists():
        # Capture privately in memory, never print secret-bearing stdout.
        reader = "const fs=require('node:fs');const yaml=require('js-yaml');process.stdout.write(JSON.stringify(yaml.load(fs.readFileSync(process.argv[1],'utf8'))));"
        previous = json.loads(subprocess.check_output([str(node), '-e', reader, str(credential_file)], cwd=runtime, text=True))
    data = configure(root, instance, args.model, plugin_dir/'plugin.mjs', previous)
    recipe = {'format': 'mms-work-recipe-v2', 'title': '任务整理示例',
        'prompt': '请把以下目标整理为三条可执行步骤，直接回复，不调用工具：{{goal}}',
        'variables': ['goal'], 'modelRequirements': {'image': False, 'reasoning': False}}
    sample = instance / 'recipes' / 'quick-plan.json'
    if not sample.exists():
        sample.parent.mkdir(exist_ok=True, mode=0o700)
        sample.write_text(json.dumps(recipe, ensure_ascii=False), encoding='utf8')
    print(f'MMS bundle verified: {len(data["routes"])} routes; {len(data["excluded"])} excluded. Instance: {instance}', flush=True)
    if args.configure_only:
        return
    cmd = [str(node), '--import', str(HERE/'observe.mjs'), str(cli), '--patch', str(instance/'mms.patch.yml'), '--profile', 'web']
    cmd += ['--no-open', '--port', str(args.port)]
    os.chdir(workspace)
    os.execve(str(node), cmd, launch_env(instance, node))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as e:
        raise SystemExit(str(e))
