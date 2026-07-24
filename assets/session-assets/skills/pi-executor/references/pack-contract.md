# Pi Executor Pack Contract

`pi-executor` consumes the shared `executor.pack.v1` emitted by:

```bash
python3 /Users/xin/auto-skills/shared-skills/executor/scripts/executor.py pack \
  --root <target-repo> \
  --task-id <task-id> \
  --commit <git-commit> \
  --title '<title>' \
  --objective '<bounded objective>' \
  --writable-file 'src/example.py' \
  --read-file 'README.md' \
  --forbidden-file '.env' \
  --success-criterion '<observable condition>' \
  --validation 'python3 -m pytest tests/test_example.py -q' \
  --write
```

Runtime normalization adds `base_commit`, `pack_path`, and `target_repo`. Validation strings are parsed with `shlex` and executed as argv without a shell. `writable_files` supports exact paths and glob patterns such as `src/**`; every changed path not matching it is rejected. `read_only_files`, `forbidden_files`, and invariant `.git/**` always outrank writable scope.

Each route attempt starts from the same detached base commit in a new worktree. A request failure may try the verified fallback route in another clean worktree. Scope failure and validation failure are implementation verdicts, not route failures, so they do not silently retry another provider.

The shared repo-local Pi cache is never a worker write surface. A pre-primed executable may be read from it; otherwise `npx` uses a private cache inside the per-run temp root.

An admissible result requires all of the following:

- at least one changed file;
- no protected or unspecified changed path;
- patch size within the configured limit;
- every Host validation command passed;
- validation did not mutate the captured source patch;
- Pi completed before wall/idle/output/repetition/global timeout.

The parent packet is an intake artifact, not an apply instruction. Patch adoption remains a Host decision.

Offline `--result` intake verifies the local patch and recorded scope/validation fields but cannot authenticate historical execution. It therefore always requires Host revalidation and cannot produce live `ready_for_intake` status.
