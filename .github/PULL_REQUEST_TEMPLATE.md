<!--
Thanks for contributing! Please use a Conventional Commit style PR title,
e.g. "fix: handle accounts without a meter" or "feat: add unread bill sensor".
This drives automated changelog and versioning.
-->

## Summary

<!-- What does this PR change and why? Link any related issues, e.g. "Closes #14". -->

## Type of change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change
- [ ] Documentation / chore

## Checklist

- [ ] `ruff check custom_components tests scripts` passes
- [ ] `ruff format --check custom_components tests scripts` passes
- [ ] `mypy` passes
- [ ] `pytest` passes and new/changed behaviour is covered by tests
- [ ] `translations/en.json` matches `strings.json`
- [ ] No real account data (customer ID, PIN, account number, postcode) in code, tests or fixtures
- [ ] I have updated documentation where relevant
