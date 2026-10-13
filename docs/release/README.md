# Release Process

## Current status (honest snapshot)

- **Packaging is not implemented yet.** There are no installers, no
  `flet build` configuration, and no CI release workflow in this repository.
  The website's download buttons currently point users at
  `https://github.com/Shadow-457/walkie-talkie/releases` (and the repo for
  source installs) — until artifacts exist there, **source install is the
  only verified installation path**.
- The app version is reported by the MCP server as `1.0.0`
  (`serverInfo.version`, `/` endpoint) — update both places if you cut a
  versioned release.

Do not advertise binaries on the site before they are built and smoke-tested.

## When packaging is added

Put platform build scripts and installer config under `packaging/`; outputs
belong in `dist/` (currently git-ignored). The natural path for this stack is
Flet's builder:

```bash
# illustrative — verify against the installed Flet version before relying on it
flet build windows   # .exe installer
flet build macos     # .dmg
flet build linux     # .deb / AppImage, per target
```

Requirements for any packaging work:

- Bundle `assets/img/logo-icon.png` and `assets/img/favicon.png` (the GUI
  loads the icon via Flet's `assets_dir`); `assets/img/logo-full.png` /
  `assets/img/logo.png` are the lockup and og:image renders.
- Pin dependencies exactly for release builds (`pip freeze`-style lock) even
  though `requirements.txt` uses bounded ranges for development.
- Verify a clean install, upgrade, and uninstall on each supported OS.

## Release checklist

1. `git status` clean; all intended changes committed.
2. `pytest` — all tests pass.
3. `python3 tools/check_site_links.py` — no broken links.
4. Manual verification per `docs/testing/README.md`.
5. Update docs whose behaviour changed (README, `docs/protocols/`, website
   pages) and bump the version strings if this is a versioned release.
6. Build artifacts (once packaging exists) and smoke-test each one — the
   artifact, not the source tree, is what users receive.
7. Tag the release; publish notes including known issues.
8. Record the release in `agents/history/`.

## Versioning

- Semantic-ish versioning: breaking protocol changes → minor/major bump plus
  a compatibility note in `docs/protocols/README.md`.
- Never replace an already-published artifact without a new version; users
  may have pinned checksums.

## Supported platforms

- Verified in development: **Linux** (this repository's environment).
- Intended: Windows and macOS via Flet — **not yet verified**; do not claim
  otherwise in release notes or on the website until tested.
