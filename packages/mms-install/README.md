# @ctrixin/mms

One command to install [MMS](https://github.com/CtriXin/multi-model-switch) on a machine that already has Node.js:

```bash
npx --yes https://github.com/CtriXin/multi-model-switch/releases/latest/download/ctrixin-mms.tgz
```

It installs the latest MMS release, then offers to open MMS Web. Accept and the browser opens while the server keeps running in the background.

## Which command should I use?

This package is the shortcut for people who already have Node.js. On a bare machine use the primary installer instead, because it bootstraps Node.js by itself:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```

Both paths run the same installer and produce the same result.

The npm registry shortcut `npx @ctrixin/mms` requires separate registry publication. The release tarball above works without an npm account and resolves the latest stable MMS release.

## Arguments

Installer options are forwarded. Selection options also accept `--ref=value` and `--channel=value`; the last selection wins. Stable resolves the published release first, then pins both installer and source to that tag:

```bash
npx --yes https://github.com/CtriXin/multi-model-switch/releases/latest/download/ctrixin-mms.tgz --channel dev        # the dev channel
npx --yes https://github.com/CtriXin/multi-model-switch/releases/latest/download/ctrixin-mms.tgz --ref v4.3.0         # pin a release or branch
npx --yes https://github.com/CtriXin/multi-model-switch/releases/latest/download/ctrixin-mms.tgz --no-launch-web      # do not open MMS Web at the end
npx --yes https://github.com/CtriXin/multi-model-switch/releases/latest/download/ctrixin-mms.tgz --dry-run            # print the plan, write nothing
npx --yes https://github.com/CtriXin/multi-model-switch/releases/latest/download/ctrixin-mms.tgz --help               # the installer's own help
```

`--channel` and `--ref` also decide which version of the installer itself is downloaded, so the script and the sources it installs always match.

## What this package does

It first resolves the stable GitHub Release (or your explicit ref), then downloads `install.sh` from the repository over HTTPS and runs it with `bash`, forwarding your arguments. It contains no install logic of its own, which is why a cached copy still installs the current MMS.

Because it downloads and executes a shell script, it is kept small and auditable: the source host is pinned to `raw.githubusercontent.com`, redirects are refused before following them, and the payload is checked before anything runs.

Temporary scripts are removed after both successful and failed runs. Network and release lookup failures stop with an error instead of silently installing a different version.

Its own version number carries no meaning about which MMS you get. It always installs the latest release unless you pass `--ref` or `--channel`.

## Requirements

Node.js 18.17 or newer, and `bash`. macOS and Linux only. On Windows, run it from WSL.

## License

Apache-2.0
