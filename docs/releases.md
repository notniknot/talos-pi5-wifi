# Local releases

There are no GitHub Actions workflows. Building and validation run locally;
GitHub may hold source, draft releases and public artifacts.

1. Keep `sources.lock.json`'s upstream and custom versions aligned, update patches,
   and commit the source. Increment `pi5.N` for changes on the same upstream.
2. Run `python3 scripts/release.py --version v1.14.2-pi5.6` on your local builder.
3. Test installation against a disposable loop disk, then boot the exact artifacts
   on hardware. Follow [the validation checklist](validation.md). Record results
   in release notes, including any skipped tests.
4. Review `build.json`, `SHA256SUMS`, and the public output directory. A dirty build
   is suitable for development, not a published release. Public files must not
   contain credentials. Do not upload all of `_out/`.
5. Publish only after validation. Example commands below require `gh` and `skopeo`
   authenticated to your own repository and GHCR. They are intentionally manual.

```sh
VERSION=v1.14.2-pi5.6
REPO=notniknot/talos-pi5-wifi
# Run from the committed source used by the build.
git tag -a "$VERSION" -m "Talos Pi 5 Wi-Fi $VERSION"
git push origin "$VERSION"
skopeo copy \
  "oci-archive:_out/releases/$VERSION/talos-pi5-wifi-$VERSION-arm64-installer.oci.tar" \
  "docker://ghcr.io/$REPO/installer:$VERSION"
gh release create "$VERSION" --repo "$REPO" --verify-tag --draft --prerelease \
  --title "Talos Pi 5 Wi-Fi $VERSION" --notes-file RELEASE_NOTES.md \
  _out/releases/"$VERSION"/*
```

Write `RELEASE_NOTES.md` with upstream version, project revision, hardware model,
exact tests and remaining limitations before running these commands. Check GHCR
package visibility if other machines need unauthenticated installer pulls. Never
reuse a version tag or publish a `latest` tag for unvalidated artifacts.

`build.json` defaults `hardware_validated` to false: a successful build cannot
prove a hardware test. Keep that build-time fact; document the later test and
artifact SHA256 values in release notes. An installer image name or source tag
alone does not certify that a release has been tested.
