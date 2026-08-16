# Release Checklist

Use this before every release.

## Pre-Release

- [ ] Update version in `pyproject.toml`
- [ ] Update `__version__` in `agent_bitcoin/__init__.py`
- [ ] Update `CHANGELOG.md` with new changes
- [ ] Run full test suite: `uv run pytest`
- [ ] Run linters: `uv run ruff check .` and `uv run black --check .`
- [ ] Build package: `uv build`
- [ ] Test installation from local build: `pip install dist/*.whl`
- [ ] LND backup: recent `./export-lnd-backup.sh` + `./verify-lnd-backup.sh` on operator nodes (see [docs/lnd-backup-restore.md](docs/lnd-backup-restore.md)); note last restore-drill date

## Release

- [ ] Commit and push changes
- [ ] Create and push git tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
- [ ] Verify GitHub Actions passed
- [ ] Check PyPI: https://pypi.org/project/agent-bitcoin/
- [ ] Announce release

## Post-Release

- [ ] Update documentation if needed
- [ ] Update example notebooks
- [ ] Notify users/community
