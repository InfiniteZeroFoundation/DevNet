# Python lint migration evidence — issue 320, first slice

Snapshot: `b1cd4d55ba2c44ec17248e9fa4a21a215b742e25` (clean tracked
`develop` tree), captured 2026-11-09 with Ruff **0.16.4**. No fixes applied.
Both commands returned **1** (findings). Each JSON records the complete
path/line/column/rule/message diagnostics, per-rule counts, and discovery
inventory. Detailed fixes/source snippets are omitted to keep evidence compact.

| Policy | Findings | Discovered files |
| --- | ---: | ---: |
| Old implicit defaults | 849 | 122 |
| Explicit agreed Python policy | 229 | 122 |

These counts were captured on Linux. Ruff disables `EXE001` on Windows and
WSL; on WSL the old-defaults report has 842 findings, omitting the seven
executable-bit findings. The agreed policy does not enable `EXE001` and still
reports 229. See [Ruff’s EXE001 documentation](https://docs.astral.sh/ruff/rules/shebang-not-executable/).

The 122 files comprise 121 Python files and `pyproject.toml`. Old Ruff defaults
also admit Markdown/notebooks and enable a much broader set of rules; on this
snapshot those extra extensions add no discovered files. The changed totals
represent policy selection, not debt resolved. E402/E741 appear under the
explicit policy; the old default rule set differs in both directions. The old
report remains deferred-debt evidence, not an ongoing CI checker or a budget.
The baseline predates the lint reporting scripts/tests added in this slice;
current CI artifacts cover those files too.

Reproduce from the modified repository root (requires git, tar, Python and uv):

```bash
python3 .github/scripts/ruff_snapshot.py /tmp/ruff-baseline
```

The recorder resolves the pinned historical SHA with `git rev-parse`, extracts
`git archive` into its own temporary directory, and never changes caller source.
It records the actual `ruff --version`, resolved source SHA, exit status,
commands, target and discovery inventory. The agreed report also records the
SHA256 of the copied policy so later policy edits cannot silently claim the
same historical configuration.

Old defaults run `uv tool run --from ruff==0.16.4 ruff check . --no-cache
--isolated --target-version py312 --output-format json`, avoiding ambient Ruff
configuration. The agreed policy copies the current repository `pyproject.toml`
into that temporary snapshot and runs without `--isolated --target-version
py312` (the configuration sets the target). Each mode also runs `--show-files`
to record discovery. Paths are normalized relative to the snapshot. Use this
slice's policy unchanged to reproduce these historical counts. Normal Git
ignore discovery remains enabled. No Python runtime version is claimed by
these lint reports; `py312` specifies Ruff's analysis target.

Suppression review (no edits):

- `tests/test_resampling_policy.py:34`: F401, intentional import side effect.
- Both `cache_model_{0,1}/services/auditor.py:14-15`: E402/F401 and E402;
  imports follow runtime `sys.path` setup. Old RUF100 calls the E402 entries
  unused because its selected rules omit E402; the agreed policy selects E402,
  so these suppressions are relevant and must not be mechanically removed.
- `cache_model_0/services/client.py:37` and
  `cache_model_1/services/client.py:33`: F401 on the example model import.
  Preserve until the example owners review intended use.

At the time of this first snapshot, remaining work was peer review and source cleanup,
with overlap coordinated across CLI/integration, example services, SDK/daemon,
and documentation work. This historical slice did not introduce blocking lint findings.
The blocking gate must also reject `invalid-syntax`: pytest only catches
syntax errors in modules it imports, so it cannot cover every example or script.


## Blocking gate

The current workflow uses `.github/scripts/ruff_check.py`. Every finding,
including `invalid-syntax`, fails the Python job and therefore `CI OK`.
Tool, configuration, unreadable-input and report failures also fail the job.
The JSON artifact upload runs even when the checker fails. This applies to
pull requests, `develop` pushes and merge groups through the existing workflow.

The final cleanup started from `1ff1bce5499c46ee9e4f9a25064fac45c4adb8be`
with 23 findings under the unchanged policy: 15 F841, three E722, three E402,
and two F401. The example aggregators explicitly retain their
`ModelArchitecture` export for compatibility. Auditor status lookups still use
False for ordinary errors, but interruption and process-exit signals propagate.
Historical JSON reports above remain unchanged; they are not finding allowances.

Before publishing the final cleanup, verify `python -m ruff check .` is clean
and run `pytest -m "not integration" -q` with the CI constraints and Ruff
installed. The checker tests exercise real clean, lint, syntax and configuration
failure cases when Ruff is installed (as in CI). Hosted PR/merge-group checks
and the post-merge `develop` run must pass before a peer confirms issue 320 is
complete. Update Discussion 74's advisory status after that change lands.
