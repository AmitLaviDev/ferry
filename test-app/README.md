# Ferry Test App

Test repository for validating Ferry's push-to-deploy loop end-to-end. Also serves
as a reference example for onboarding repositories with Ferry.

## Prerequisites

Before Ferry can deploy from this repo, the following must exist:

- **ECR repository** `ferry-test/hello-world` in the target AWS account
- **Lambda function** `ferry-test-hello-world` in the target AWS account
- **OIDC IAM role** with trust policy allowing this repo's GitHub Actions
- **Ferry GitHub App** installed on this repository
- **Repository secret** `AWS_ROLE_ARN` set to the OIDC role ARN

## ferry.yaml

Ferry reads `ferry.yaml` from the repo root to discover resources:

```yaml
version: 1
lambdas:
  - name: hello-world
    source_dir: lambdas/hello-world
    ecr_repo: ferry-test/hello-world
    function_name: ferry-test-hello-world
    runtime: python3.12
```

Each Lambda entry maps a source directory to an ECR repo and AWS function name.
Ferry detects changes under `source_dir` and triggers a build-and-deploy cycle.

## Workflow

The `.github/workflows/ferry-lambdas.yml` workflow is triggered by Ferry App via
`workflow_dispatch`. It:

1. Parses the Ferry dispatch payload into a build matrix
2. Builds a container image using Ferry's Magic Dockerfile
3. Pushes the image to ECR
4. Updates the Lambda function code

The workflow references Ferry's composite actions from `AmitLaviDev/ferry@main`.
AWS authentication uses OIDC (no long-lived credentials).

## Directory Structure

```
.
├── ferry.yaml                              # Ferry configuration
├── .github/workflows/ferry-lambdas.yml     # GHA workflow for Lambda deploys
├── lambdas/
│   └── hello-world/
│       ├── main.py                         # Lambda handler
│       └── requirements.txt                # Python dependencies (empty)
└── README.md
```
