# Releasing the Coding Guidelines

This is the canonical maintainer procedure for publishing a versioned build of
the Safety-Critical Rust Coding Guidelines to GitHub Pages.

The release candidate is an exact commit from the default branch's history. A
later merge to `main` does not change that commit or invalidate a successful
preflight. Release Preflight verifies the candidate against the live FLS;
Deploy then builds the tagged commit against its committed `src/spec.lock`
without retrieving the live FLS.

For the policy rationale and trust boundaries, see the
[FLS audit and release policy](docs/fls-audit.md#release-preflight-and-deploy).

## Prerequisites

- Obtain repository write access for workflow dispatch and tag creation.
- Merge every change intended for the release.
- Choose a release tag accepted by the Deploy trigger, which currently matches
  `*.*.*`. This filter is not a semantic-version validator.
- Identify the exact commit to release. It must be reachable from the default
  branch, but it does not have to remain the current `main` head.

Use a full lowercase 40-character commit SHA throughout this procedure. With an
up-to-date local checkout, the current `main` head can be recorded with:

```shell
git fetch origin main
VERSION="1.2.3"
RELEASE_SHA="$(git rev-parse origin/main)"
printf '%s\n' "$RELEASE_SHA"
```

Replace the example version with the approved release name. Do not proceed until
the printed SHA is the commit intended for the release.

## Run Release Preflight

To run the preflight in the GitHub interface:

1. Open the repository's **Actions** tab.
2. Select **Release Preflight**.
3. Select **Run workflow**.
4. In the **Branch** dropdown, select the branch whose head is `RELEASE_SHA`.
   GitHub may label this dropdown **Use workflow from**.
5. Enter `RELEASE_SHA` in the `release_sha` field.
6. Select **Run workflow** and wait for the entire run to finish.

The branch dropdown establishes the workflow run's `GITHUB_SHA`; the
`release_sha` input independently states the intended release commit. Preflight
fails if those values differ, if the input is not a full lowercase SHA, or if
the commit is not reachable from the default branch.

The equivalent GitHub CLI command for a candidate at the head of `main` is:

```shell
gh workflow run release-preflight.yml \
  --ref main \
  -f release_sha="$RELEASE_SHA"
```

Confirm that the workflow succeeded and that the exact commit has a successful
`release-preflight` commit status. Do not rely only on another build or check
with a similar name.

## Handle a Moving Main Branch

If `main` advances after GitHub creates the preflight run, the run remains bound
to its original `GITHUB_SHA`. The original commit remains a valid candidate as
long as it is still reachable from `main`.

If `main` advances before the run is dispatched, decide whether the new commit
belongs in the release:

| Release decision | Action |
| --- | --- |
| Include the new merge | Record the new `main` SHA and dispatch a new preflight against `main`. |
| Keep the frozen candidate | Push a temporary branch whose head is the original SHA and dispatch preflight against that branch. |

For example, create a temporary remote branch for a frozen candidate with:

```shell
CANDIDATE_BRANCH="release-candidate-$VERSION"
git push origin "$RELEASE_SHA:refs/heads/$CANDIDATE_BRANCH"
```

Select `release-candidate-1.2.3` in the GitHub branch dropdown and enter the same
`RELEASE_SHA`. Wait for the full preflight to finish before deleting the branch:

```shell
git push origin --delete "$CANDIDATE_BRANCH"
```

Do not reset `main` or create the version tag merely to provide a dispatch ref.

## Create the Version Tag

For a tag's first publication, Deploy must begin authorization while the latest
`release-preflight` status on `RELEASE_SHA` is successful and no more than 24
hours old. Do not wait until the edge of that window. A timestamp up to five
minutes in the future is accepted for GitHub and runner clock skew.

Create the version tag on `RELEASE_SHA`, not on the current branch implicitly.
For example:

```shell
git tag "$VERSION" "$RELEASE_SHA"
test "$(git rev-parse "$VERSION^{}")" = "$RELEASE_SHA"
git push origin "refs/tags/$VERSION"
```

The tag push automatically starts the Deploy workflow. If using GitHub's release
interface instead, verify that the new tag targets `RELEASE_SHA`, rather than
assuming it should target the latest `main` head.

## Verify Deployment

Open the tag-triggered Deploy run and confirm, in order:

1. **Authorize release** accepts the tagged SHA.
2. The complete reusable build succeeds in FLS-offline mode.
3. **Deploy to GitHub Pages** succeeds.
4. The tagged commit receives a successful `deploy/<tag>` commit status.
5. The published site contains the intended release.

The offline input is specific to FLS data: the documentation build reads the
tagged commit's `src/spec.lock` instead of fetching the live FLS. The workflow
still uses GitHub Actions, locked package availability, Rust toolchains,
artifacts, and GitHub Pages. It is not an air-gapped or byte-for-byte
reproducible build.

## Recover From Failure

Use the first applicable recovery:

| Failure | Recovery |
| --- | --- |
| Selected branch and `release_sha` differ | Decide which commit is intended, then dispatch again with a branch whose head is that exact SHA. |
| Candidate is not reachable from `main` | Merge it through the normal review path or do not release it. |
| Preflight fails live FLS freshness | Reconcile `src/spec.lock` in a reviewed change, then preflight the new commit. |
| Preflight is older than 24 hours | Refresh preflight on the existing tag as described below, then rerun Deploy. |
| Deploy fails because of a transient service error | Rerun the same Deploy workflow for the unchanged tag and commit. |
| The committed source or lock must change | Create a reviewed fix commit, run a new preflight, and use a new version tag. |

Do not move an existing version tag to recover a failure. If a deployment has
already succeeded, its tag-specific `deploy/<tag>` status authorizes future
redeployment of that same tag and commit without another live FLS check. That
authorization does not expire.

### Refresh an expired preflight

If the version tag already exists but its successful preflight has expired,
dispatch Release Preflight directly against the tag with the GitHub CLI:

```shell
git fetch origin "refs/tags/$VERSION:refs/tags/$VERSION"
RELEASE_SHA="$(git rev-parse "$VERSION^{}")"
gh workflow run release-preflight.yml \
  --ref "$VERSION" \
  -f release_sha="$RELEASE_SHA"
```

After that run succeeds, rerun the original Deploy workflow for the unchanged
tag, either in GitHub Actions or with `gh run rerun <deploy-run-id>`. Do not push
the tag again.

The release procedure creates lightweight tags. For an annotated tag, confirm
that the dispatch resolves `GITHUB_SHA` to `RELEASE_SHA`; the workflow's exact
SHA guard fails closed if it does not. In that case, use the temporary-branch
fallback below.

If an interface cannot select a tag as the workflow ref, create a temporary
branch at `RELEASE_SHA`, dispatch preflight against that branch, and delete the
branch after the run finishes. The branch is a user-interface fallback, not a
requirement of the release protocol.

Commit statuses are workflow evidence, not signed attestations. Repository
administrators and trusted workflows with status-write permission are inside
the release trust boundary.
