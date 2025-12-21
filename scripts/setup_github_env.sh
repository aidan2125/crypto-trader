#!/usr/bin/env bash
set -euo pipefail

# Helper to create a protected GitHub Environment and add the DISCORD_WEBHOOK_URL secret
# Requirements: `gh` CLI installed and authenticated (run `gh auth login` first).

progname=$(basename "$0")

usage(){
  cat <<EOF
Usage: $progname [owner/repo] [env-name]

If owner/repo is omitted the script will try to detect it from git remote.
Defaults:
  env-name = alerts

This script will prompt you (securely) for the webhook value and then:
  1. create the GitHub Environment
  2. add the secret named DISCORD_WEBHOOK_URL to that environment

It does NOT print or store the webhook locally.
EOF
}

REPO_ARG=${1:-}
ENV_NAME=${2:-alerts}

if [[ "$REPO_ARG" == "-h" || "$REPO_ARG" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh CLI not found. Install from https://cli.github.com/ and run 'gh auth login'." >&2
  exit 2
fi

if [[ -z "$REPO_ARG" ]]; then
  # try to discover repo from git
  if git rev-parse --git-dir >/dev/null 2>&1; then
    origin_url=$(git remote get-url origin 2>/dev/null || true)
    if [[ -n "$origin_url" ]]; then
      # convert git@github.com:OWNER/REPO.git or https://github.com/OWNER/REPO.git
      repo=$(echo "$origin_url" | sed -E 's#(git@|https?://)([^/:]+)[:/]+([^/]+)/(.+)#\3/\4#' | sed 's/\.git$//')
      REPO_ARG=${repo}
      echo "Detected repo: $REPO_ARG"
    fi
  fi
fi

if [[ -z "$REPO_ARG" ]]; then
  read -rp "Repository (owner/repo): " REPO_ARG
fi

echo "Environment name: $ENV_NAME"

read -rsp "Paste DISCORD_WEBHOOK_URL (input hidden): " WEBHOOK
echo

if [[ -z "$WEBHOOK" ]]; then
  echo "No webhook provided; aborting." >&2
  exit 3
fi

echo "Creating environment '$ENV_NAME' in repository $REPO_ARG..."
# create environment via API (idempotent)
gh api --method PUT "/repos/${REPO_ARG}/environments/${ENV_NAME}"

echo "Adding secret DISCORD_WEBHOOK_URL to environment '$ENV_NAME'..."
# gh secret set supports --env and --repo
gh secret set DISCORD_WEBHOOK_URL --env "$ENV_NAME" --repo "$REPO_ARG" --body "$WEBHOOK"

echo "Done. The environment '$ENV_NAME' was created and the secret was added."
echo "On GitHub, protect the environment with reviewers if you want manual approvals."

exit 0
