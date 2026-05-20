# generator pipeline

Generator pipeline is split by responsibility instead of by accumulated output hacks.

Current modules:

- `css_geometry.py`: computes page and section geometry for CSS output from the
  canonical model.

Ownership rule:

1. Add new rendering behaviour here first.
2. Keep the behaviour covered by pipeline tests.
3. Remove old compatibility branches when pipeline owns the complete responsibility.



