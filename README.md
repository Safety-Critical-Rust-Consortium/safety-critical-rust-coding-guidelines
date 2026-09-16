# Safety-Critical Rust Coding Guidelines

This repository contains Coding Guidelines for writing Safety Critical Rust, developed by the [Safety Critical Rust Consortium][safety-critical-rust-consortium].

- View the [rendered guidelines](https://coding-guidelines.arewesafetycriticalyet.org/) online.
- Check out the [project goals](GOALS.md).

## Building the coding guidelines

The Safety-Critical Rust Coding Guidelines website uses `Sphinx` and `Sphinx-Needs` to build a rendered version of the coding guidelines, and `uv` to install and manage Python dependencies (including Sphinx itself). To simplify building the rendered version, we created a script called `make.py` that takes care of invoking Sphinx with the right flags.

Build the rendered version by running:

```shell
uv run --frozen make.py
```

The required uv version is pinned in `pyproject.toml`. Until a tooling owner is
assigned, periodic uv upgrades are a shared maintainer responsibility: update
the uv runtime pin, the `uv_build` range, the Netlify `UV_VERSION` in
`netlify.toml`, and `uv.lock` together in one PR. Netlify uses that
repository-controlled configuration instead of its UI build command so deploy
previews install the same uv version as local and GitHub Actions builds.

By default, Sphinx uses incremental rebuilds to generate the content that
changed since the last invocation. If you notice a problem with incremental
rebuilds, pass the `-c` flag to clear the existing artifacts before
building `uv run --frozen make.py -c`.

The following output is generated:

- A rendered version in `build/html/`
- A machine-parseable artifact in `build/html/needs.json`
- A record of the contents with checksums in `build/html/guidelines-ids.json`

<!-- TODO: Pete LeVasseur The `needs.json` file could use some cleaning up and some description here of the contents. -->

### Running builds offline

If you're working without internet access or want to avoid reaching out to remote resources, you can pass the `--offline` flag:

```shell
uv run --frozen make.py --offline
```

With the required dependencies available, this makes FLS validation use the
committed `src/spec.lock` instead of fetching current FLS paragraph data. It
does not make the complete command air-gapped or byte-for-byte reproducible:
`uv` may need to retrieve locked dependencies, and hosted workflows continue to
use GitHub services.

Use `--offline` if you are running `make.py` frequently during development, to prevent rate-limiting due to repeated requests to the [FLS](https://rust-lang.github.io/fls/paragraph-ids.json).

### Checking an out-of-date spec lock file

It is fairly common for `src/spec.lock` to become outdated while a contributor is developing an unrelated guideline.

Local and normal CI builds print a prominent end-of-build drift summary without
failing solely because of it; CI also creates a warning annotation and preserves
the detailed report as an artifact. If the live FLS remains unavailable or
unusable after bounded retries, these non-enforcing builds validate references
against the committed lock and report that freshness was not checked. A
guideline that references an FLS item newer than the committed lock still fails
validation; synchronize the lock in a reviewed change rather than bypassing the
reference check. Missing or malformed lock data and invalid FLS references
still fail the build.

CI enforcement differs by workflow; see the [FLS CI enforcement policy](docs/fls-audit.md#ci-enforcement-policy) for the blocking and nonblocking paths.

#### Enforcing freshness locally

Nightly and Release Preflight enforce freshness. To run the same check locally:

```shell
uv run --frozen make.py --enforce-spec-lock-diff
```

Freshness enforcement requires live FLS data and cannot be combined with
`--offline`. The deprecated `--ignore-spec-lock-diff` option remains a no-op for
command-line compatibility; non-enforcing behavior is already the default.

#### Auditing the difference

When the build detects a difference in `spec.lock`, a log is saved in `/tmp/fls_diff_<random>.txt` which you can use to audit the differences.

To see a quick summary of the difference:

```shell
uv run python scripts/fls_audit.py --summary-only
```

To see a full report of the difference:

```shell
uv run python scripts/fls_audit.py
```

See [FLS audit docs](docs/fls-audit.md) for the full workflow, snapshots, advanced options, and
the steps to rationalize and update `src/spec.lock`, including the rationalization checklist.

## Releasing

Release maintainers must run `Release Preflight` for the exact intended commit
before creating a version tag. Follow [RELEASING.md](RELEASING.md), the
canonical release procedure, for selecting a candidate, handling a moving
`main` branch, tagging the preflighted commit, verifying deployment, and
recovering from failures.

## What we're working on

The Coding Guidelines [work items board](https://github.com/orgs/Safety-Critical-Rust-Consortium/projects/4) shows tickets actively being worked on, and tickets you can pick up.

## Contributing

Read the [CONTRIBUTING.md](./CONTRIBUTING.md) and [REVIEWING.md](./REVIEWING.md) for the details on contributing and reviewing guidelines.

## [Code of Conduct][code-of-conduct]

The [Rust Foundation][rust-foundation] has adopted a Code of Conduct that we
expect project participants to adhere to. Please read [the full
text][code-of-conduct] so that you can understand what actions will and will not
be tolerated.

## Licenses

Rust is primarily distributed under the terms of both the MIT license and the
Apache License (Version 2.0), with documentation portions covered by the
Creative Commons Attribution 4.0 International license..

See [LICENSE-APACHE](LICENSE-APACHE), [LICENSE-MIT](LICENSE-MIT),
[LICENSE-documentation](LICENSE-documentation), and
[COPYRIGHT](COPYRIGHT) for details.

You can also read more under the Foundation's [intellectual property
policy][ip-policy].

## Other Policies

Read other Rust Foundation [policies][foundation-website].

[code-of-conduct]: https://foundation.rust-lang.org/policies/code-of-conduct/
[foundation-website]: https://foundation.rust-lang.org
[ip-policy]: https://foundation.rust-lang.org/policies/intellectual-property-policy/
[media-guide and trademark]: https://foundation.rust-lang.org/policies/logo-policy-and-media-guide/
[rust-foundation]: https://foundation.rust-lang.org/
[safety-critical-rust-consortium]: https://github.com/Safety-Critical-Rust-Consortium/safety-critical-rust-consortium
