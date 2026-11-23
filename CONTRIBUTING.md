# Contributing

## Setup

```sh
uv venv --python 3.14
uv pip install -r requirements_test.txt
```

## Checks (the gate)

```sh
ruff check custom_components tests scripts
ruff format --check custom_components tests scripts
mypy
pytest
```

Or run the hooks with `pre-commit run --all-files`.

## Conventions

- Conventional Commits (`feat:`, `fix:`, `chore:` …). release-please reads
  these to cut versions; do not hand-edit versions.
- Edit `strings.json`, then copy it to `translations/en.json`.
- When bumping `united-utilities`, change both `manifest.json` and
  `requirements_test.txt`.
- No real account data in tests.
- GitHub Actions `uses:` are pinned to a commit SHA with a `# vX.Y.Z` comment.
