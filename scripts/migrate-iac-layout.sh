#!/usr/bin/env bash
# migrate-iac-layout.sh -- Ferry IaC directory restructure and state migration
#
# Moves 4 Terraform projects to the new directory layout and migrates their
# S3 backend state keys. Assumes providers.tf files already have updated keys
# (committed in a prior code change).
#
# Order: backend -> ecr -> oidc -> shared (OIDC before shared because shared
# references OIDC remote state).
#
# Usage: ./scripts/migrate-iac-layout.sh
#   Run from the repo root. Requires: terraform, git, AWS credentials.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IAC="$REPO_ROOT/iac"

echo "Ferry IaC Directory Restructure and State Migration"
echo "===================================================="
echo ""

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

command -v terraform >/dev/null 2>&1 || { echo "ERROR: terraform is not installed or not in PATH"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "ERROR: git is not installed or not in PATH"; exit 1; }

# Verify source directories exist (not yet moved)
for dir in global/aws/backend global/aws/ecr global/aws/oidc staging/aws/shared; do
    [[ -d "$IAC/$dir" ]] || { echo "ERROR: Expected source directory not found: $IAC/$dir"; exit 1; }
done

echo "Pre-flight checks passed."
echo ""

# ---------------------------------------------------------------------------
# Helper function: migrate a single Terraform project
# ---------------------------------------------------------------------------

migrate_project() {
    local src="$1"
    local dst="$2"
    local label="$3"
    local step="$4"

    echo "[$step] Migrating $label..."
    echo "  Source: iac/$src"
    echo "  Target: iac/$dst"

    # Step 1: Delete .terraform/ from source (clean slate)
    if [[ -d "$IAC/$src/.terraform" ]]; then
        echo "  Removing .terraform/ from source..."
        rm -rf "$IAC/$src/.terraform"
    fi

    # Step 2: Create target parent directory
    mkdir -p "$(dirname "$IAC/$dst")"

    # Step 3: git mv source to target
    git mv "$IAC/$src" "$IAC/$dst"

    # Step 4: terraform init with state migration
    echo "  Running terraform init -migrate-state..."
    terraform -chdir="$IAC/$dst" init -migrate-state -force-copy -input=false

    # Step 5: terraform plan to validate no changes
    echo "  Running terraform plan to validate..."
    terraform -chdir="$IAC/$dst" plan -input=false

    echo "[$step] $label: OK"
    echo ""
}

# ---------------------------------------------------------------------------
# Create target parent directories
# ---------------------------------------------------------------------------

mkdir -p "$IAC/global/cloud/aws"
mkdir -p "$IAC/aws/staging"

# ---------------------------------------------------------------------------
# Migrate projects in order
# ---------------------------------------------------------------------------

migrate_project "global/aws/backend" "global/cloud/aws/backend" "backend" "1/4"
migrate_project "global/aws/ecr"     "global/cloud/aws/ecr"     "ecr"     "2/4"
migrate_project "global/aws/oidc"    "global/cloud/aws/oidc"    "oidc"    "3/4"
migrate_project "staging/aws/shared" "aws/staging/shared"        "shared"  "4/4"

# ---------------------------------------------------------------------------
# Clean up empty directories
# ---------------------------------------------------------------------------

echo "Cleaning up empty directories..."
rmdir "$IAC/global/aws" 2>/dev/null && echo "  Removed iac/global/aws/" || true
rmdir "$IAC/staging/aws" 2>/dev/null && echo "  Removed iac/staging/aws/" || true
rmdir "$IAC/staging" 2>/dev/null && echo "  Removed iac/staging/" || true

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "===================================================="
echo "Migration complete!"
echo ""
echo "Projects migrated:"
echo "  [1/4] backend -> iac/global/cloud/aws/backend"
echo "  [2/4] ecr     -> iac/global/cloud/aws/ecr"
echo "  [3/4] oidc    -> iac/global/cloud/aws/oidc"
echo "  [4/4] shared  -> iac/aws/staging/shared"
echo ""
echo "Next steps:"
echo "  1. Review changes: git status"
echo "  2. Commit the directory moves: git add -A && git commit -m 'chore: restructure IaC directory layout'"
echo "===================================================="
