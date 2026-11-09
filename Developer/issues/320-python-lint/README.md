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

Remaining work: peer review of this slice and separately scoped source cleanup,
with overlap coordinated across CLI/integration, example services, SDK/daemon,
and documentation work. No blocking lint findings policy is introduced here.
