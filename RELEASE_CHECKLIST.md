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

## Release

- [ ] Commit and push changes
- [ ] Create and push git tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
- [ ] Verify GitHub Actions passed
- [ ] Check TestPyPI: https://test.pypi.org/project/agent-bitcoin/
- [ ] Announce release

## Post-Release

- [ ] Update documentation if needed
- [ ] Update example notebooks
- [ ] Notify users/community
