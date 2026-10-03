# Releasing Inky

A release is a version tag. CI builds every installer into a **draft** release; a maintainer tries it and presses Publish.

## 1. Before the tag

- [ ] `main` has everything, and CI is green on it.
- [ ] The version is bumped in the five places `scripts/check_versions.py` checks (`pyproject.toml`, `inky/__init__.py`, `desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/Cargo.toml`, `desktop/package.json`). Run `python scripts/check_versions.py`.
- [ ] `CHANGELOG.md` has a section for the version, with today's date, and the compare links at the bottom.
- [ ] Unit tests pass: `python -m unittest`.
- [ ] The release gate passes on this computer: `python -m tests.journeys five newuser do chat share` (see [acceptance.md](acceptance.md)). If DuckDuckGo is pausing searches after many runs, E-bike Hunter may learn fewer sites; rerun it later with `INKY_FIVE="E-bike Hunter"`.

## 2. Tag

```bash
git tag v0.1.1 -m "Inky 0.1.1"
git push origin v0.1.1
```

[release.yml](../.github/workflows/release.yml) builds macOS (Apple Silicon and Intel), Windows (setup .exe and .msi) and Linux (.AppImage, .deb, .rpm), adds build provenance and `SHA256SUMS.txt`, and leaves the release as a draft. The job fails if the tag and the app's version disagree.

## 3. Try the draft

On clean machines, or at least clean user accounts:

- [ ] **macOS 15 or later (Apple Silicon), and an Intel Mac if you can.** Open the .dmg and drag Inky to Applications. Open it, and expect the "can't verify" prompt; then System Settings → Privacy & Security → **Open Anyway**. Setup, then **Try it now**: books should be found in under a minute.
- [ ] **Windows 11.** Run the setup .exe, then "Windows protected your PC" → More info → **Run anyway**. Same test.
- [ ] **Ubuntu 24.04.** The .deb or the AppImage. Same test.
- [ ] The README's download table matches the file names in the release.

## 4. Publish

Edit the draft: paste the CHANGELOG section as the notes, then press **Publish release**. `releases/latest` now points to it.

## Signing and stores

- **Updates inside the app are already on.** Release builds are signed with the updater key; its public half is in `tauri.conf.json`, and the private half is in the repo's Actions secrets (`TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`) and with the maintainer, backed up offline. If that key is lost, installed copies can't be updated any more and people have to reinstall by hand. The app reads `releases/latest/download/latest.json`, so publishing a release is what rolls it out.
- **macOS signing and notarization** are built in: add the Apple secrets once and every release is signed with the Developer ID and notarized. Until then it's ad-hoc signed. Steps and the local `notarize-macos.sh`: [desktop/README.md](../desktop/README.md#signing-and-notarizing).
- **Windows signing:** [SignPath Foundation](https://signpath.org/apply) signs open-source projects for free. Inky qualifies: MIT, public repo, public releases, and installers built in public CI. Once approved:
  1. Add the secret `SIGNPATH_API_TOKEN`, and note the organization id, project slug and signing policy slug SignPath gives you.
  2. In the Windows job of [release.yml](../.github/workflows/release.yml), build without uploading. Upload `bundle/nsis/*.exe` and `bundle/msi/*.msi` with `actions/upload-artifact` (with an `id`), then sign them with `SignPath/github-action-submit-signing-request@v2` (`github-artifact-id: ${{ steps.<id>.outputs.artifact-id }}`, `output-artifact-directory`).
  3. Signing changes the files, so make their in-app update signatures again with `npx tauri signer sign <file>` (it reads `TAURI_SIGNING_PRIVATE_KEY`). Then upload the signed installers, their `.sig` files and the Windows entry of `latest.json` to the draft.

  An Azure Trusted Signing or OV certificate works too, through `bundle.windows.signCommand`. That signs during the build, so step 3 isn't needed.
- **Package managers:** winget after a release or two; a Homebrew cask once the app is notarized.
