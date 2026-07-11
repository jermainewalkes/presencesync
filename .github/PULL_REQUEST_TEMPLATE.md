## What does this change?

<!-- A short description of the change and the problem it solves. Link any related issue. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / internal cleanup
- [ ] Documentation

## Checklist

- [ ] The test suite passes (`./venv/bin/python -m unittest discover -s tests`).
- [ ] New behaviour has tests, and any change to `core/sync.py` keeps the loop-prevention
      cases in `tests/test_sync.py` green.
- [ ] Platform front ends I could not run were compile-checked (`python -m py_compile ...`).
- [ ] No secrets, tokens or `org-config.json` contents are included in the diff.
- [ ] Comments are minimal and professional, and user-facing labels use Title Case.

## Platforms tested

<!-- e.g. macOS 14.5; Windows not tested -->
