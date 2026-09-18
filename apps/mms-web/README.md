# MMS Pilot

React / TypeScript client for the local MMS service. The v4 release bundles compiled assets; end users run `mms web --open` without a frontend build.

- [用户安装与使用](../../docs/mms-web/GETTING-STARTED.md)
- [产品与技术交接](../../docs/mms-web/NEXT-PHASE.md)
- [API](../../docs/mms-web/API.md)

## Development

Use Node.js 24 LTS and Python 3.11+. Pi 0.85.1 is the verified native runtime. In this directory, run `npm ci --workspaces=false`, then `npm run dev`. Start the backend separately from the repository root with `python3 -m mms_web --port 8765 --state-root /path/to/task-owned-state`.

The Vite dev server proxies only the local MMS API. `?preview=1` explicitly opens demonstration data and cannot substitute for a real Pi validation.

Run `python3 scripts/build_mms_web_release.py` from the repo root to rebuild `mms_web_static`. Its manifest binds the bundle to frontend source and lockfile. Commit the generated assets with the source change when releasing.

File references are original local paths. Clipboard images without a path are stored privately. Do not bring back mandatory dataset uploads. See the handoff for privacy, configuration and adapter boundaries.
