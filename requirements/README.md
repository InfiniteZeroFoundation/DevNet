# dincli runtime lock

`dincli-runtime.txt` pins the full runtime dependency tree for the node image and
Python CI. Its only project input is `[project].dependencies` in
[`pyproject.toml`](../pyproject.toml). The universal lock keeps platform markers
so installers select the entries that apply to their environment. Test tools and
the CPU Torch install are managed separately by CI. Public `pip install .` and
`pip install -e .` still use the dependency ranges from the package metadata.

Run from the repository on Linux with Git, Bash, Python 3 with `venv`, and access
to public PyPI. The script installs uv 0.10.9 in a temporary virtual environment,
then resolves for Python 3.12. uv can fetch a Python 3.12 interpreter if none can
be found. Local pip/uv configuration, extra indexes and CI constraints are not
used.

```bash
# Regenerate after editing project dependencies. Reuse compatible pins.
scripts/lock-dincli-runtime.sh

# Check that the tracked lock is present and generation leaves no diff.
scripts/lock-dincli-runtime.sh --check

# Intentionally refresh one package, or refresh the entire lock.
scripts/lock-dincli-runtime.sh --upgrade-package requests
scripts/lock-dincli-runtime.sh --upgrade
```

Do not edit the lock by hand. Review any diff, run the node and Python CI tests,
and commit the regenerated lock with the dependency change. The check uses Git's
index as its baseline and leaves any regenerated diff available for review. A
compatible range edit can legitimately leave the lock unchanged.

## Migration from the node-only pins

The first resolution tried all five previous pins as temporary constraints.
Normal generation without those constraints kept the versions but removed
constraint provenance. The migrated lock retains `typer==0.20.0`,
`platformdirs==4.5.0` and `py-cid==0.5.0`. Two pins changed intentionally:

- `python-dotenv` moved from 1.0.1 to 1.2.4 for the upstream fix to
  [CVE-2026-28684](https://github.com/theskumar/python-dotenv/security/advisories/GHSA-mf9w-mj56-hr94).
- `web3` moved from 7.10.0 to 7.16.0 to pick up the fix for
  [CVE-2026-40072](https://github.com/ApeWorX/web3.py/security/advisories/GHSA-5hr4-253g-cpx2)
  without a major-version API upgrade. A separate follow-up advisory
  [CVE-2026-111171](https://github.com/advisories/GHSA-w8h5-xcmp-474f) still lists
  7.16.0 as affected. Triage belongs in the
  [DevNet dependency security follow-up](https://github.com/InfiniteZeroFoundation/DevNet/issues/298).
