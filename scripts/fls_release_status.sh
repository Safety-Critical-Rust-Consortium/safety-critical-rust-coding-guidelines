#!/usr/bin/env bash
set -euo pipefail

PREFLIGHT_CONTEXT="release-preflight"
PREFLIGHT_MAX_AGE_SECONDS="${PREFLIGHT_MAX_AGE_SECONDS:-86400}"
PREFLIGHT_FUTURE_TOLERANCE_SECONDS="${PREFLIGHT_FUTURE_TOLERANCE_SECONDS:-300}"

require_common_environment() {
  : "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
  : "${GITHUB_SHA:?GITHUB_SHA is required}"
  : "${GH_TOKEN:?GH_TOKEN is required}"
}

post_status() {
  local context="$1"
  local state="$2"
  local description="$3"

  require_common_environment
  : "${GITHUB_SERVER_URL:?GITHUB_SERVER_URL is required}"
  : "${GITHUB_RUN_ID:?GITHUB_RUN_ID is required}"
  if (( ${#context} > 100 )); then
    echo "::error::Commit status context exceeds GitHub's 100-character limit."
    return 1
  fi

  gh api --method POST "repos/$GITHUB_REPOSITORY/statuses/$GITHUB_SHA" \
    -f state="$state" \
    -f context="$context" \
    -f description="$description" \
    -f target_url="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
}

format_duration() {
  local seconds="$1"
  if (( seconds > 0 && seconds % 3600 == 0 )); then
    printf "%ss (%sh)" "$seconds" "$((seconds / 3600))"
  elif (( seconds > 0 && seconds % 60 == 0 )); then
    printf "%ss (%sm)" "$seconds" "$((seconds / 60))"
  else
    printf "%ss" "$seconds"
  fi
}

authorize_release() {
  require_common_environment
  : "${GITHUB_REF_NAME:?GITHUB_REF_NAME is required}"
  if [[ ! "$PREFLIGHT_MAX_AGE_SECONDS" =~ ^[0-9]+$ || ! "$PREFLIGHT_FUTURE_TOLERANCE_SECONDS" =~ ^[0-9]+$ ]]; then
    echo "::error::Release preflight age and clock-skew limits must be nonnegative integers."
    return 1
  fi

  local deploy_context="deploy/$GITHUB_REF_NAME"
  if (( ${#deploy_context} > 100 )); then
    echo "::error::Deployment status context exceeds GitHub's 100-character limit."
    return 1
  fi

  local status_rows
  status_rows=$(gh api --method GET --paginate -f per_page=100 \
    "repos/$GITHUB_REPOSITORY/commits/$GITHUB_SHA/status" \
    --jq '.statuses[] | [.context, .state, .created_at] | @tsv')

  local deploy_state=""
  local preflight_state=""
  local preflight_created=""
  local context current_state created_at
  while IFS=$'\t' read -r context current_state created_at; do
    if [[ "$context" == "$deploy_context" ]]; then
      deploy_state="$current_state"
    elif [[ "$context" == "$PREFLIGHT_CONTEXT" ]]; then
      preflight_state="$current_state"
      preflight_created="$created_at"
    fi
  done <<<"$status_rows"

  if [[ "$deploy_state" == "success" ]]; then
    echo "Prior successful deployment authorizes $GITHUB_REF_NAME at $GITHUB_SHA."
    return 0
  fi
  if [[ -z "$preflight_state" ]]; then
    echo "::error::No release preflight status exists for $GITHUB_SHA."
    return 1
  fi
  if [[ "$preflight_state" != "success" ]]; then
    echo "::error::Latest release preflight status is $preflight_state, not success."
    return 1
  fi

  local preflight_epoch
  if ! preflight_epoch=$(date -u -d "$preflight_created" +%s); then
    echo "::error::Release preflight status has an invalid timestamp: $preflight_created"
    return 1
  fi
  local now_epoch
  now_epoch=$(date -u +%s)
  local preflight_age=$((now_epoch - preflight_epoch))
  if (( preflight_age < -PREFLIGHT_FUTURE_TOLERANCE_SECONDS )); then
    echo "::error::Release preflight timestamp exceeds the configured $(format_duration "$PREFLIGHT_FUTURE_TOLERANCE_SECONDS") future clock-skew tolerance."
    return 1
  fi
  if (( preflight_age > PREFLIGHT_MAX_AGE_SECONDS )); then
    echo "::error::Release preflight status is outside the configured $(format_duration "$PREFLIGHT_MAX_AGE_SECONDS") publication window."
    return 1
  fi

  echo "Recent release preflight authorizes $GITHUB_REF_NAME at $GITHUB_SHA."
}

record_preflight_result() {
  : "${VALIDATE_RESULT:?VALIDATE_RESULT is required}"
  : "${BUILD_RESULT:?BUILD_RESULT is required}"

  local state="failure"
  local description="Release preflight failed"
  if [[ "$VALIDATE_RESULT" == "success" && "$BUILD_RESULT" == "success" ]]; then
    state="success"
    description="Release preflight passed"
  fi
  post_status "$PREFLIGHT_CONTEXT" "$state" "$description"
  if [[ "$state" == "success" ]]; then
    return 0
  fi
  return 1
}

case "${1:-}" in
  authorize)
    authorize_release
    ;;
  pending)
    post_status "$PREFLIGHT_CONTEXT" "pending" "Release preflight is running"
    ;;
  preflight-result)
    record_preflight_result
    ;;
  deployed)
    : "${GITHUB_REF_NAME:?GITHUB_REF_NAME is required}"
    post_status "deploy/$GITHUB_REF_NAME" "success" "Tag $GITHUB_REF_NAME deployed successfully"
    ;;
  *)
    echo "Usage: $0 {authorize|pending|preflight-result|deployed}" >&2
    exit 2
    ;;
esac
