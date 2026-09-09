# @ctrixin/mms

One command to install [MMS](https://github.com/CtriXin/multi-model-switch) on a machine that already has Node.js:

```bash
npx @ctrixin/mms
```

It installs the latest MMS release, then offers to open MMS Web. Accept and the browser opens while the server keeps running in the background.

## Which command should I use?

This package is the shortcut for people who already have Node.js. On a bare machine use the primary installer instead, because it bootstraps Node.js by itself:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```

Both paths run the same installer and produce the same result.

## Arguments

Every argument is passed straight through to the installer:

```bash
npx @ctrixin/mms --channel dev        # the dev channel
npx @ctrixin/mms --ref v4.3.0         # pin a release or branch
npx @ctrixin/mms --no-launch-web      # do not open MMS Web at the end
npx @ctrixin/mms --dry-run            # print the plan, write nothing
npx @ctrixin/mms --help               # the installer's own help
```

`--channel` and `--ref` also decide which version of the installer itself is downloaded, so the script and the sources it installs always match.

## What this package does

It downloads `install.sh` from the repository over HTTPS and runs it with `bash`, forwarding your arguments. It contains no install logic of its own, which is why a cached copy still installs the current MMS.

Because it downloads and executes a shell script, it is kept small and auditable: the source host is pinned to `raw.githubusercontent.com`, redirects off that host are refused, and the payload is checked before anything runs.

Its own version number carries no meaning about which MMS you get. It always installs the latest release unless you pass `--ref` or `--channel`.

## Requirements

Node.js 18.17 or newer, and `bash`. macOS and Linux only. On Windows, run it from WSL.

## License

Apache-2.0
