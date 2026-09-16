import sys
from pathlib import Path

import pytest

from builder import build_cli


@pytest.mark.parametrize(
    ("arguments", "enforce_freshness"),
    [
        ([], False),
        (["--ignore-spec-lock-diff"], False),
        (["--enforce-spec-lock-diff"], True),
    ],
)
def test_local_build_freshness_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    arguments: list[str],
    enforce_freshness: bool,
) -> None:
    policies = []

    def capture_build(
        _root: Path,
        _builder: str,
        _clear: bool,
        _serve: bool,
        _debug: bool,
        _offline: bool,
        spec_lock_consistency_check: bool,
        _validate_urls: bool,
    ) -> None:
        policies.append(spec_lock_consistency_check)

    monkeypatch.setattr(sys, "argv", ["make.py", *arguments])
    monkeypatch.setattr(build_cli, "build_docs", capture_build)

    build_cli.main(tmp_path)

    assert policies == [enforce_freshness]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--offline", "--enforce-spec-lock-diff"], "freshness cannot be enforced offline"),
        (
            ["--ignore-spec-lock-diff", "--enforce-spec-lock-diff"],
            "not allowed with argument --ignore-spec-lock-diff",
        ),
    ],
)
def test_rejects_conflicting_freshness_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    message: str,
) -> None:
    monkeypatch.setattr(sys, "argv", ["make.py", *arguments])

    with pytest.raises(SystemExit, match="2"):
        build_cli.main(tmp_path)

    assert message in capsys.readouterr().err


def test_compatibility_flag_prints_notice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["make.py", "--ignore-spec-lock-diff"])
    monkeypatch.setattr(build_cli, "build_docs", lambda *_args: None)

    build_cli.main(tmp_path)

    assert "--ignore-spec-lock-diff is deprecated and has no effect" in capsys.readouterr().err
