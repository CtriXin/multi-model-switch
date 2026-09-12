"""The npx wrapper is published to npm, so its shape is checked here rather
than only at publish time. Nothing in this file reaches the network."""

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "packages" / "mms-install"
MANIFEST = PACKAGE_DIR / "package.json"
ENTRY = PACKAGE_DIR / "bin" / "mms-install.mjs"
WINDOWS_BOOTSTRAP = PACKAGE_DIR / "bin" / "install.ps1"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_package_is_publishable_as_a_public_scoped_package():
    manifest = _manifest()

    assert manifest["name"] == "@ctrixin/mms"
    assert manifest["publishConfig"]["access"] == "public"
    assert manifest["license"] == "Apache-2.0"
    assert manifest["bin"] == {"mms-install": "bin/mms-install.mjs"}
    assert "bin" in manifest["files"]
    assert "README.md" in manifest["files"]
    assert manifest["repository"]["directory"] == "packages/mms-install"


def test_package_declares_the_platforms_it_can_actually_run_on():
    manifest = _manifest()

    # global fetch and the node: prefix both need a modern runtime
    assert manifest["engines"]["node"] == ">=18.17"
    assert manifest["os"] == ["darwin", "linux", "win32"]


def test_entrypoint_is_executable_and_parses():
    assert ENTRY.exists()
    assert os.access(ENTRY, os.X_OK), "npm needs the bin file to be executable"
    assert ENTRY.read_text(encoding="utf-8").startswith("#!/usr/bin/env node\n")

    node = shutil.which("node")
    if node is None:  # pragma: no cover - node is present in this repo's toolchain
        return
    subprocess.run([node, "--check", str(ENTRY)], check=True, capture_output=True)


def test_wrapper_pins_the_source_host_and_verifies_the_payload():
    text = ENTRY.read_text(encoding="utf-8")

    assert 'const RAW_HOST = "raw.githubusercontent.com"' in text
    assert 'const REPO = "CtriXin/multi-model-switch"' in text
    # a redirect away from the pinned host must abort, not be followed silently
    assert "refusing a redirect off" in text
    # the payload is checked before it is executed
    assert 'REPO_NAME="multi-model-switch"' in text
    assert "does not look like the MMS installer" in text


def test_wrapper_holds_no_install_logic_of_its_own():
    """Install behavior belongs in install.sh so a cached wrapper stays correct."""
    text = ENTRY.read_text(encoding="utf-8")

    for leaked in ("~/.mms", "npm install -g", "pi-coding-agent", "MMS_CONFIG_ROOT"):
        assert leaked not in text, leaked
    assert len(text.splitlines()) < 140


def test_wrapper_keeps_the_script_and_the_installed_sources_on_one_ref():
    text = ENTRY.read_text(encoding="utf-8")

    for flag in ("--ref", "--channel", "--dev", "--canary"):
        assert flag in text, flag
    assert "function parseArgs" in text


def test_wrapper_routes_windows_to_a_readable_preview_bootstrap():
    text = ENTRY.read_text(encoding="utf-8")

    assert 'process.platform === "win32"' in text
    assert "runWindowsBootstrap" in text
    assert "MMS Windows Native Preview bootstrap" in text


def test_windows_bootstrap_is_packaged_and_has_no_unbounded_shell_fallback():
    text = WINDOWS_BOOTSTRAP.read_text(encoding="utf-8")
    assert "MMS Windows Native Preview bootstrap" in text
    assert "Invoke-WebRequest" in text and "Expand-Archive" in text
    assert "MMS_CONFIG_ROOT" in text and "MMS_STATE_ROOT" in text
    assert "taskkill" not in text.lower()


def test_windows_wrapper_translates_ref_and_dry_run_to_powershell_flags():
    _node('''
      import assert from 'node:assert/strict';
      import {runWindowsBootstrap} from %s;
      const calls=[];
      const root=await import('node:os').then(m=>m.tmpdir());
      const code=runWindowsBootstrap('MMS Windows Native Preview bootstrap', ['--ref','main','--dry-run'], (cmd,args)=>{calls.push([cmd,args]);return {status:0};}, root);
      assert.equal(code,0); assert.equal(calls[0][0],'powershell.exe');
      assert.ok(calls[0][1].includes('-Ref') && calls[0][1].includes('main') && calls[0][1].includes('-DryRun'));
    ''' % json.dumps(ENTRY.as_uri()))


def test_package_is_part_of_the_repo_workspaces():
    root_manifest = json.loads((ROOT_DIR / "package.json").read_text(encoding="utf-8"))

    assert "packages/*" in root_manifest["workspaces"]
    assert root_manifest.get("private") is True, "only the wrapper is published"


def _node(source):
    node = shutil.which('node')
    assert node, 'Node is required for the npm entrypoint regression'
    imports = 'import {parseArgs,resolveInstaller,runInstaller} from ' + json.dumps(ENTRY.as_uri()) + ';\n'
    subprocess.run([node, '--input-type=module', '-e', imports + source], check=True, capture_output=True, text=True)


def test_selection_precedence_and_equals_normalization():
    _node('''
      import assert from 'node:assert/strict';
      assert.deepEqual(parseArgs(['--ref=v4.1.0','--channel=dev','--dry-run']), {selection:'dev',forwarded:['--dry-run'],literalRef:false});
      assert.equal(parseArgs(['--dev','--ref','v4.8.0']).selection, 'v4.8.0');
      assert.equal(parseArgs(['--canary','--stable']).selection, 'stable');
      assert.throws(()=>parseArgs(['--channel=bogus']));
      assert.throws(()=>parseArgs(['--ref']));
      assert.throws(()=>parseArgs(['--ref=../../main']));
    ''')


def test_stable_resolves_release_and_pins_script_and_sources():
    _node('''
      import assert from 'node:assert/strict';
      const urls=[];
      const plan=await resolveInstaller(['--dry-run'],async(url,options)=>{
        urls.push(url);assert.equal(options.redirect,'error');assert.ok(options.signal);
        return {ok:true,url,json:async()=>({tag_name:'v4.8.0'}),text:async()=> '#!/bin/bash\\nREPO_NAME="multi-model-switch"'};
      });
      assert.equal(urls.length,2);assert.ok(urls[0].endsWith('/releases/latest'));
      assert.ok(urls[1].includes('/v4.8.0/install.sh'));
      assert.deepEqual(plan.args,['--dry-run','--ref','v4.8.0']);
    ''')


def test_lookup_failure_and_untrusted_download_fail_closed():
    _node('''
      import assert from 'node:assert/strict';
      let calls=0;
      await assert.rejects(resolveInstaller([],async()=>{calls++;return {ok:false,status:429};}));
      assert.equal(calls,1);
      await assert.rejects(resolveInstaller(['--ref=v4.8.0'],async()=>({ok:true,url:'https://other.example/install.sh',text:async()=>''})));
      await assert.rejects(resolveInstaller(['--ref=v4.8.0'],async()=>({ok:true,text:async()=>'<html>wrong</html>'})));
    ''')


def test_temporary_installer_is_removed_on_every_exit():
    _node('''
      import assert from 'node:assert/strict';
      import {mkdtempSync,readdirSync,rmSync,readFileSync} from 'node:fs';
      import {tmpdir} from 'node:os';import {join} from 'node:path';
      const root=mkdtempSync(join(tmpdir(),'mms-npx-test-'));
      try {
        for(const status of [0,7,null]) {
          const code=runInstaller('fixture', ['--dry-run'], (cmd,args)=>{
            assert.equal(cmd,'bash');assert.equal(readFileSync(args[0],'utf8'),'fixture');return {status};
          },root);
          assert.equal(code,status===null?1:status);assert.deepEqual(readdirSync(root),[]);
        }
        assert.throws(()=>runInstaller('fixture',[],()=>({error:new Error('no bash')}),root));
        assert.deepEqual(readdirSync(root),[]);
      } finally {rmSync(root,{recursive:true,force:true});}
    ''')


def test_explicit_ref_named_stable_is_not_changed_to_a_release():
    _node('''
      import assert from 'node:assert/strict';
      const urls=[];
      const plan=await resolveInstaller(['--ref=stable'],async url=>{urls.push(url);return {ok:true,text:async()=> '#!/bin/bash\\nREPO_NAME="multi-model-switch"'};});
      assert.equal(urls.length,1);assert.equal(plan.ref,'stable');
    ''')


def test_npm_symlink_bin_executes_the_cli_instead_of_silently_exiting(tmp_path):
    link=tmp_path/'mms-install'
    link.symlink_to(ENTRY)
    result=subprocess.run([shutil.which('node'),str(link),'--channel=bogus'],capture_output=True,text=True)
    assert result.returncode==1
    assert '--channel must be' in result.stderr
