import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

from scripts.reviewer_bot_core import reconcile_replay_policy
from scripts.reviewer_bot_lib import reconcile_payloads


def test_legacy_reconcile_compatibility_surfaces_are_removed():
    assert not hasattr(reconcile_payloads, "artifact_expected_name")
    assert not hasattr(reconcile_payloads, "artifact_expected_payload_name")
    assert not hasattr(reconcile_payloads, "expected_observer_identity")
    assert not hasattr(reconcile_replay_policy, "decide_observer_noop")


def test_parse_deferred_context_payload_rejects_legacy_schema_versions_and_observer_noop():
    with pytest.raises(RuntimeError, match="schema_version is not accepted"):
        reconcile_payloads.parse_deferred_context_payload(
            {
                "schema_version": 2,
                "source_event_name": "issue_comment",
                "source_event_action": "created",
                "source_event_key": "issue_comment:210",
                "pr_number": 42,
                "comment_id": 210,
                "comment_class": "command_only",
                "has_non_command_text": False,
                "source_body_digest": "digest",
                "source_created_at": "2026-03-17T10:00:00Z",
                "actor_login": "alice",
                "source_run_id": 1,
                "source_run_attempt": 1,
            }
        )
    with pytest.raises(RuntimeError, match="schema_version is not accepted"):
        reconcile_payloads.parse_deferred_context_payload(
            {
                "schema_version": 1,
                "kind": "observer_noop",
                "reason": "trusted_direct_same_repo_human_comment",
                "source_event_name": "issue_comment",
                "source_event_action": "created",
                "source_event_key": "issue_comment:210",
                "pr_number": 42,
            }
        )


def test_observer_noop_positive_fixtures_are_gone():
    assert not Path("tests/fixtures/observer_payloads/helper_pr_comment_trusted_direct_noop.json").exists()
    assert not Path("tests/fixtures/observer_payloads/helper_pr_comment_automation_noop.json").exists()


def test_reconcile_and_overdue_sources_no_longer_keep_legacy_paths_alive():
    reconcile_text = Path("scripts/reviewer_bot_lib/reconcile.py").read_text(encoding="utf-8")
    payloads_text = Path("scripts/reviewer_bot_lib/reconcile_payloads.py").read_text(encoding="utf-8")
    overdue_text = Path("scripts/reviewer_bot_lib/overdue.py").read_text(encoding="utf-8")

    assert "_handle_observer_noop_workflow_run" not in reconcile_text
    assert "ObserverNoopPayload" not in payloads_text
    assert "_LegacyDeferredIssueCommentPayloadV2" not in payloads_text
    assert "_LegacyDeferredReviewCommentPayloadV2" not in payloads_text
    assert "_TRANSITION_NOTICE_FALLBACK_FIRST_LINE" not in overdue_text
    assert "or first_line ==" not in overdue_text


def test_final_reconcile_replay_fixture_no_longer_has_noop_row():
    matrix = json.loads(
        Path("tests/fixtures/equivalence/reconcile_replay/scenario_matrix.json").read_text(encoding="utf-8")
    )

    assert "noop_artifact" not in {row["scenario_id"] for row in matrix["scenarios"]}
