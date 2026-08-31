import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import exts.coding_guidelines as coding_guidelines
from exts.coding_guidelines import fls_checks, fls_linking


def app(
    tmp_path: Path,
    *,
    enforce: bool = False,
    offline: bool = False,
    fls_url: str = fls_checks.fls_paragraph_ids_url,
) -> SimpleNamespace:
    return SimpleNamespace(
        confdir=tmp_path,
        config=SimpleNamespace(
            enable_spec_lock_consistency=enforce,
            offline=offline,
            fls_paragraph_ids_url=fls_url,
        ),
    )


def fls_data() -> dict:
    return {
        "documents": [
            {
                "title": "FLS",
                "sections": [
                    {
                        "id": "fls_section",
                        "number": "1",
                        "link": "section.html",
                        "paragraphs": [
                            {
                                "id": "fls_123456789",
                                "number": "1:1",
                                "link": "paragraph.html",
                                "checksum": "checksum",
                            }
                        ],
                    }
                ],
            }
        ]
    }


def response(status: int, value: dict) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(value).encode()
    return result


def test_lock_file_is_required_even_when_freshness_is_not_enforced(tmp_path: Path) -> None:
    with pytest.raises(fls_checks.FLSValidationError, match="No FLS lock file"):
        fls_checks.check_fls_lock_consistency(app(tmp_path), object(), {})


def test_lock_file_must_be_valid_json_even_when_freshness_is_not_enforced(tmp_path: Path) -> None:
    (tmp_path / "spec.lock").write_text("not json\n", encoding="utf-8")

    with pytest.raises(fls_checks.FLSValidationError, match="Failed to read FLS lock file"):
        fls_checks.check_fls_lock_consistency(app(tmp_path), object(), {})


@pytest.mark.parametrize("value", [{}, {"documents": []}])
def test_lock_file_must_have_documents_when_freshness_is_not_enforced(tmp_path: Path, value: dict) -> None:
    (tmp_path / "spec.lock").write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(fls_checks.FLSValidationError, match="documents must be a nonempty list"):
        fls_checks.check_fls_lock_consistency(app(tmp_path), object(), {})


def test_disabled_enforcement_still_computes_freshness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "spec.lock").write_text(json.dumps({"documents": [{"sections": []}]}), encoding="utf-8")
    monkeypatch.setattr(fls_checks, "SphinxNeedsData", lambda _env: SimpleNamespace(get_needs_view=lambda: {}))
    monkeypatch.setattr(fls_checks, "get_tqdm", lambda *, iterable, **_kwargs: iterable)
    monkeypatch.setattr(fls_checks.fls_diff, "extract_paragraphs", lambda value: value)
    monkeypatch.setattr(
        fls_checks.fls_diff,
        "diff_paragraphs",
        lambda _live, _locked: {"added": [{"id": 1}], "removed": [], "changed": [{"id": 2}]},
    )
    monkeypatch.setattr(fls_checks.fls_diff, "has_differences", lambda _diff: True)
    monkeypatch.setattr(fls_checks.fls_diff, "build_detailed_differences", lambda _diff, _guidelines: (["change"], []))
    monkeypatch.setattr(fls_checks.fls_diff, "write_detailed_report", lambda _details: tmp_path / "details")
    monkeypatch.setattr(fls_checks.fls_diff, "build_summary", lambda _affected, _changed: ["change"])

    assert fls_checks.check_fls_lock_consistency(app(tmp_path), object(), {"live": {}}) == (True, ["change"])


def test_nonblocking_drift_records_prominent_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = app(tmp_path)
    (tmp_path / "spec.lock").write_text(json.dumps({"documents": [{"sections": []}]}), encoding="utf-8")
    monkeypatch.setattr(fls_checks, "SphinxNeedsData", lambda _env: SimpleNamespace(get_needs_view=lambda: {}))
    monkeypatch.setattr(fls_checks, "get_tqdm", lambda *, iterable, **_kwargs: iterable)
    monkeypatch.setattr(fls_checks.fls_diff, "extract_paragraphs", lambda current: current)
    monkeypatch.setattr(
        fls_checks.fls_diff,
        "diff_paragraphs",
        lambda _live, _locked: {"added": [{"id": 1}], "removed": [{"id": 2}], "changed": [{"id": 3}]},
    )
    monkeypatch.setattr(fls_checks.fls_diff, "has_differences", lambda _diff: True)
    monkeypatch.setattr(fls_checks.fls_diff, "build_detailed_differences", lambda _diff, _guidelines: (["change"], []))
    monkeypatch.setattr(fls_checks.fls_diff, "write_detailed_report", lambda _details: tmp_path / "details")
    monkeypatch.setattr(fls_checks.fls_diff, "build_summary", lambda _affected, _changed: ["change"])

    assert fls_checks.check_fls_lock_consistency(value, object(), {"live": {}}) == (True, ["change"])
    assert value.fls_notices == [
        "spec.lock drift detected; build continued (added: 1, removed: 1, changed: 1). "
        f"Details: {tmp_path / 'details'}. "
        "Run `uv run --frozen make.py --enforce-spec-lock-diff` to make this blocking."
    ]


def test_detailed_report_write_failure_records_notice_without_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = app(tmp_path)
    (tmp_path / "spec.lock").write_text(json.dumps({"documents": [{"sections": []}]}), encoding="utf-8")
    monkeypatch.setattr(fls_checks, "SphinxNeedsData", lambda _env: SimpleNamespace(get_needs_view=lambda: {}))
    monkeypatch.setattr(fls_checks, "get_tqdm", lambda *, iterable, **_kwargs: iterable)
    monkeypatch.setattr(fls_checks.fls_diff, "extract_paragraphs", lambda value: value)
    monkeypatch.setattr(
        fls_checks.fls_diff,
        "diff_paragraphs",
        lambda _live, _locked: {"added": [], "removed": [], "changed": [{"id": 1}]},
    )
    monkeypatch.setattr(fls_checks.fls_diff, "has_differences", lambda _diff: True)
    monkeypatch.setattr(fls_checks.fls_diff, "build_detailed_differences", lambda _diff, _guidelines: (["change"], []))

    def fail_to_write(_details: list[str]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(fls_checks.fls_diff, "write_detailed_report", fail_to_write)
    monkeypatch.setattr(fls_checks.fls_diff, "build_summary", lambda _affected, _changed: ["change"])
    caplog.set_level(logging.WARNING, logger="sphinx")

    assert fls_checks.check_fls_lock_consistency(value, object(), {"live": {}}) == (True, ["change"])
    assert caplog.records == []
    assert value.fls_notices == [
        "spec.lock drift detected; build continued (added: 0, removed: 0, changed: 1). "
        "Detailed report unavailable. "
        "Run `uv run --frozen make.py --enforce-spec-lock-diff` to make this blocking."
    ]


def test_check_fls_ignores_only_detected_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    value = app(tmp_path)
    env = SimpleNamespace(config=SimpleNamespace(offline=False))
    monkeypatch.setattr(fls_checks, "check_fls_exists_and_valid_format", lambda _app, _env: None)
    monkeypatch.setattr(
        fls_checks,
        "gather_fls_paragraph_ids",
        lambda _app, _url, *, offline: ({}, {"live": {}}),
    )
    monkeypatch.setattr(fls_checks, "check_fls_lock_consistency", lambda _app, _env, _raw: (True, ["change"]))
    monkeypatch.setattr(fls_checks, "check_fls_ids_correct", lambda _app, _env, _ids: None)
    monkeypatch.setattr(fls_checks, "read_fls_ignore_list", lambda _app: [])
    monkeypatch.setattr(fls_checks, "insert_fls_coverage", lambda _app, _env, _ids: None)
    monkeypatch.setattr(fls_checks, "calculate_fls_coverage", lambda _ids, _ignored: {})
    monkeypatch.setattr(fls_checks, "log_coverage_report", lambda _coverage: None)

    fls_checks.check_fls(value, env)

    value.config.enable_spec_lock_consistency = True
    with pytest.raises(fls_checks.FLSValidationError, match="specification has changed"):
        fls_checks.check_fls(value, env)


def test_live_fls_fetch_retries_timeouts_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = fls_data()
    outcomes: list[Exception | requests.Response] = [
        requests.Timeout("first timeout"),
        requests.Timeout("second timeout"),
        response(200, expected),
    ]
    calls = []
    sleeps = []

    def get(url: str, *, timeout: tuple[int, int]) -> requests.Response:
        calls.append((url, timeout))
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(fls_checks.requests, "get", get)
    monkeypatch.setattr(fls_checks.time, "sleep", sleeps.append)

    assert fls_checks.fetch_live_fls_data("https://example.test/fls.json") == expected
    assert calls == [("https://example.test/fls.json", (5, 30))] * 3
    assert sleeps == [1, 2]


def test_live_fls_fetch_retries_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = fls_data()
    outcomes = [response(503, {}), response(200, expected)]
    sleeps = []

    monkeypatch.setattr(fls_checks.requests, "get", lambda _url, *, timeout: outcomes.pop(0))
    monkeypatch.setattr(fls_checks.time, "sleep", sleeps.append)

    assert fls_checks.fetch_live_fls_data("https://example.test/fls.json") == expected
    assert sleeps == [1]


def test_live_fls_fetch_honors_retry_after_on_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = fls_data()
    unavailable = response(503, {})
    unavailable.headers["Retry-After"] = "2"
    outcomes = [unavailable, response(200, expected)]
    sleeps = []

    monkeypatch.setattr(fls_checks.requests, "get", lambda _url, *, timeout: outcomes.pop(0))
    monkeypatch.setattr(fls_checks.time, "sleep", sleeps.append)

    assert fls_checks.fetch_live_fls_data("https://example.test/fls.json") == expected
    assert sleeps == [2]


def test_live_fls_fetch_retries_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = fls_data()
    outcomes = [response(429, {}), response(200, expected)]
    sleeps = []

    monkeypatch.setattr(fls_checks.requests, "get", lambda _url, *, timeout: outcomes.pop(0))
    monkeypatch.setattr(fls_checks.time, "sleep", sleeps.append)

    assert fls_checks.fetch_live_fls_data("https://example.test/fls.json") == expected
    assert sleeps == [1]


def test_live_fls_fetch_honors_bounded_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = fls_data()
    rate_limited = response(429, {})
    rate_limited.headers["Retry-After"] = "2"
    outcomes = [rate_limited, response(200, expected)]
    sleeps = []

    monkeypatch.setattr(fls_checks.requests, "get", lambda _url, *, timeout: outcomes.pop(0))
    monkeypatch.setattr(fls_checks.time, "sleep", sleeps.append)

    assert fls_checks.fetch_live_fls_data("https://example.test/fls.json") == expected
    assert sleeps == [2]


@pytest.mark.parametrize(
    ("retry_budget", "retry_after"),
    [
        (fls_checks.FLS_FETCH_NONBLOCKING_RETRY_BUDGET_SECONDS, 60),
        (fls_checks.FLS_FETCH_ENFORCING_RETRY_BUDGET_SECONDS, 120),
    ],
    ids=["nonblocking", "enforcing"],
)
def test_live_fls_fetch_rejects_retry_after_over_budget(
    monkeypatch: pytest.MonkeyPatch, retry_budget: int, retry_after: int
) -> None:
    calls = []
    rate_limited = response(429, {})
    rate_limited.headers["Retry-After"] = str(retry_after)

    def get(_url: str, *, timeout: tuple[int, int]) -> requests.Response:
        calls.append(timeout)
        return rate_limited

    monkeypatch.setattr(fls_checks.requests, "get", get)
    monkeypatch.setattr(fls_checks.time, "sleep", lambda _delay: pytest.fail("retry budget exceeded"))

    assert (
        fls_checks.fetch_live_fls_data(
            "https://example.test/fls.json", retry_budget_seconds=retry_budget
        )
        is None
    )
    assert calls == [(5, 30)]


def test_live_fls_fetch_honors_enforcing_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = fls_data()
    rate_limited = response(429, {})
    rate_limited.headers["Retry-After"] = "60"
    outcomes = [rate_limited, response(200, expected)]
    sleeps = []

    monkeypatch.setattr(fls_checks.requests, "get", lambda _url, *, timeout: outcomes.pop(0))
    monkeypatch.setattr(fls_checks.time, "sleep", sleeps.append)

    assert (
        fls_checks.fetch_live_fls_data(
            "https://example.test/fls.json",
            retry_budget_seconds=fls_checks.FLS_FETCH_ENFORCING_RETRY_BUDGET_SECONDS,
        )
        == expected
    )
    assert sleeps == [60]


def test_live_fls_fetch_does_not_retry_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def get(_url: str, *, timeout: tuple[int, int]) -> requests.Response:
        calls.append(timeout)
        return response(404, {})

    monkeypatch.setattr(fls_checks.requests, "get", get)
    monkeypatch.setattr(fls_checks.time, "sleep", lambda _delay: pytest.fail("client error retried"))

    assert fls_checks.fetch_live_fls_data("https://example.test/fls.json") is None
    assert calls == [(5, 30)]


def test_live_fls_fetch_does_not_retry_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    malformed = response(200, {})
    malformed._content = b"{"

    def get(_url: str, *, timeout: tuple[int, int]) -> requests.Response:
        calls.append(timeout)
        return malformed

    monkeypatch.setattr(fls_checks.requests, "get", get)
    monkeypatch.setattr(fls_checks.time, "sleep", lambda _delay: pytest.fail("malformed data retried"))

    assert fls_checks.fetch_live_fls_data("https://example.test/fls.json") is None
    assert calls == [(5, 30)]


@pytest.mark.parametrize(
    ("enforce", "expected_budget"),
    [
        (False, fls_checks.FLS_FETCH_NONBLOCKING_RETRY_BUDGET_SECONDS),
        (True, fls_checks.FLS_FETCH_ENFORCING_RETRY_BUDGET_SECONDS),
    ],
)
def test_gather_uses_mode_specific_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    enforce: bool,
    expected_budget: int,
) -> None:
    captured = []

    def fetch(_url: str, *, retry_budget_seconds: int) -> dict:
        captured.append(retry_budget_seconds)
        return fls_data()

    monkeypatch.setattr(fls_checks, "fetch_live_fls_data", fetch)

    ids, raw_data = fls_checks.gather_fls_paragraph_ids(
        app(tmp_path, enforce=enforce), "https://example.test/configured.json"
    )

    assert captured == [expected_budget]
    assert "fls_123456789" in ids
    assert raw_data == fls_data()


def test_check_fls_uses_configured_source_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured_url = "https://example.test/configured.json"
    value = app(tmp_path, enforce=True, fls_url=configured_url)
    env = SimpleNamespace(config=SimpleNamespace(offline=False))
    calls = []

    monkeypatch.setattr(fls_checks, "check_fls_exists_and_valid_format", lambda _app, _env: None)

    def gather(_app, url: str, *, offline: bool):
        calls.append((url, offline))
        return {}, None

    monkeypatch.setattr(fls_checks, "gather_fls_paragraph_ids", gather)

    with pytest.raises(fls_checks.FLSValidationError, match=configured_url):
        fls_checks.check_fls(value, env)

    assert calls == [(configured_url, False)]


def test_nonblocking_build_succeeds_after_transient_timeouts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected = fls_data()
    outcomes: list[Exception | requests.Response] = [
        requests.Timeout("first timeout"),
        requests.Timeout("second timeout"),
        response(200, expected),
    ]
    calls = []
    checked_ids = []

    def get(_url: str, *, timeout: tuple[int, int]) -> requests.Response:
        calls.append(timeout)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    value = app(tmp_path)
    env = SimpleNamespace(config=SimpleNamespace(offline=False))
    monkeypatch.setattr(fls_checks.requests, "get", get)
    monkeypatch.setattr(fls_checks.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(fls_checks, "check_fls_exists_and_valid_format", lambda _app, _env: None)
    monkeypatch.setattr(fls_checks, "check_fls_lock_consistency", lambda _app, _env, _raw: (False, []))
    monkeypatch.setattr(fls_checks, "check_fls_ids_correct", lambda _app, _env, ids: checked_ids.append(ids))
    monkeypatch.setattr(fls_checks, "read_fls_ignore_list", lambda _app: [])
    monkeypatch.setattr(fls_checks, "insert_fls_coverage", lambda _app, _env, _ids: None)
    monkeypatch.setattr(fls_checks, "calculate_fls_coverage", lambda _ids, _ignored: {})
    monkeypatch.setattr(fls_checks, "log_coverage_report", lambda _coverage: None)

    fls_checks.check_fls(value, env)

    assert calls == [(5, 30)] * 3
    assert set(checked_ids[0]) == {"fls_section", "fls_123456789"}
    assert value.fls_urls["fls_123456789"].endswith("paragraph.html")
    assert not hasattr(value, "fls_notices")


@pytest.mark.parametrize(
    ("live_result", "expected_calls"),
    [
        (requests.ConnectionError("unavailable"), 3),
        ({"documents": []}, 1),
        ({"foo": 1}, 1),
        ({"documents": [{"title": "FLS", "sections": []}]}, 1),
        ({"documents": [{"title": "FLS", "sections": ["oops"]}]}, 1),
    ],
    ids=[
        "network-error",
        "empty-documents",
        "missing-documents",
        "empty-sections",
        "malformed-sections",
    ],
)
def test_nonblocking_live_failure_uses_lock_without_sphinx_warnings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    live_result: Exception | dict,
    expected_calls: int,
) -> None:
    locked = fls_data()
    (tmp_path / "spec.lock").write_text(json.dumps(locked), encoding="utf-8")
    value = app(tmp_path)
    env = SimpleNamespace(config=SimpleNamespace(offline=False))
    calls = []
    checked_ids = []

    def get(_url: str, *, timeout: tuple[int, int]) -> requests.Response:
        calls.append(timeout)
        if isinstance(live_result, Exception):
            raise live_result
        return response(200, live_result)

    monkeypatch.setattr(fls_checks.requests, "get", get)
    monkeypatch.setattr(fls_checks.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(fls_checks, "check_fls_exists_and_valid_format", lambda _app, _env: None)
    monkeypatch.setattr(
        fls_checks,
        "check_fls_lock_consistency",
        lambda *_args: pytest.fail("freshness comparison ran without live data"),
    )
    monkeypatch.setattr(fls_checks, "check_fls_ids_correct", lambda _app, _env, ids: checked_ids.append(ids))
    monkeypatch.setattr(fls_checks, "read_fls_ignore_list", lambda _app: [])
    monkeypatch.setattr(fls_checks, "insert_fls_coverage", lambda _app, _env, _ids: None)
    monkeypatch.setattr(fls_checks, "calculate_fls_coverage", lambda _ids, _ignored: {})
    monkeypatch.setattr(fls_checks, "log_coverage_report", lambda _coverage: None)
    caplog.set_level(logging.WARNING, logger="sphinx")

    fls_checks.check_fls(value, env)

    assert calls == [(5, 30)] * expected_calls
    assert set(checked_ids[0]) == {"fls_section", "fls_123456789"}
    assert value.fls_urls["fls_123456789"].endswith("paragraph.html")
    assert value.fls_notices == [
        "Live FLS unavailable or unusable; freshness was not checked. "
        "References were validated against the committed src/spec.lock."
    ]

    value.outdir = tmp_path / "html"
    value.outdir.mkdir()
    monkeypatch.setattr(
        fls_linking,
        "load_fls_ids",
        lambda _app: pytest.fail("HTML linking fetched FLS IDs a second time"),
    )
    fls_linking.post_process_html(value)
    assert caplog.records == []


def test_nonblocking_fetch_failure_requires_valid_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value = app(tmp_path)
    env = SimpleNamespace(config=SimpleNamespace(offline=False))
    monkeypatch.setattr(fls_checks, "check_fls_exists_and_valid_format", lambda _app, _env: None)
    monkeypatch.setattr(fls_checks, "fetch_live_fls_data", lambda _url: None)

    with pytest.raises(
        fls_checks.FLSValidationError,
        match="Failed to retrieve the live FLS and read or parse the committed FLS lock",
    ):
        fls_checks.check_fls(value, env)


def test_enforced_fetch_failure_remains_blocking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value = app(tmp_path, enforce=True)
    env = SimpleNamespace(config=SimpleNamespace(offline=False))
    calls = []

    def fail_fetch(_url: str, *, timeout: tuple[int, int]) -> None:
        calls.append(timeout)
        raise requests.ConnectionError("unavailable")

    monkeypatch.setattr(fls_checks.requests, "get", fail_fetch)
    monkeypatch.setattr(fls_checks.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(fls_checks, "check_fls_exists_and_valid_format", lambda _app, _env: None)

    with pytest.raises(fls_checks.FLSValidationError, match="Failed to retrieve or parse"):
        fls_checks.check_fls(value, env)

    assert calls == [(5, 30)] * 3
    assert not hasattr(value, "fls_notices")


def test_build_finished_prints_fls_notices(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    value = SimpleNamespace(
        outdir=tmp_path,
        config=SimpleNamespace(debug=False),
        fls_notices=["spec.lock drift detected; build continued"],
    )
    monkeypatch.setattr(coding_guidelines, "get_tqdm", lambda *, iterable, **_kwargs: iterable)

    coding_guidelines.on_build_finished(value, None)

    assert "FLS NOTICE: spec.lock drift detected; build continued" in capsys.readouterr().out
