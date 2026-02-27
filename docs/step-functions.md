# Step Functions Workflows

The Step Functions workflow deploys Amazon States Language (ASL) definitions to AWS Step Functions state machines. Ferry performs variable substitution on the definition file, computes a content hash for skip detection, and publishes a new version of the state machine.

## ferry.yaml Configuration

Define your state machines in the `step_functions` section of `ferry.yaml`:

```yaml
step_functions:
  - name: order-workflow                  # Required: logical name (used for logging/display)
    source_dir: workflows/order           # Required: directory containing the definition file
    state_machine_name: OrderWorkflow     # Required: AWS state machine name
    definition_file: definition.asl.json  # Required: ASL file name, relative to source_dir
```

### Field Reference

| Field                | Required | Description |
|----------------------|----------|-------------|
| `name`               | Yes      | Logical name for the resource. Used in logs and PR status. |
| `source_dir`         | Yes      | Path to the directory containing the definition file, relative to repo root. Ferry detects changes by watching files under this path. |
| `state_machine_name` | Yes      | The name of the state machine in AWS. Used to look up the state machine ARN for deployment. |
| `definition_file`    | Yes      | The ASL definition file name, relative to `source_dir`. |

## Workflow File

Create `.github/workflows/ferry-step_functions.yml` in your repository. The file name must be exactly `ferry-step_functions.yml` -- Ferry dispatches to this name and a mismatch causes a silent 404.

```yaml
# .github/workflows/ferry-step_functions.yml
# Ferry Step Functions deployment workflow
# Triggered by Ferry App via workflow_dispatch when definition files change

name: Ferry Step Functions

on:
  workflow_dispatch:
    inputs:
      payload:
        description: "Ferry dispatch payload (JSON)"  # Sent by Ferry App
        required: true

# OIDC requires id-token:write to request the JWT
# contents:read is needed to check out the repository
permissions:
  id-token: write
  contents: read

jobs:
  # Step 1: Parse the dispatch payload into a matrix
  setup:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.parse.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4

      - name: Parse Ferry payload
        id: parse
        uses: ./action/setup                          # Ferry setup composite action
        with:
          payload: ${{ inputs.payload }}               # Raw JSON from workflow_dispatch

  # Step 2: Deploy each state machine in parallel
  deploy:
    needs: setup
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.setup.outputs.matrix) }}
      fail-fast: false                                # Deploy all resources even if one fails
    steps:
      - uses: actions/checkout@v4

      # Deploy: update state machine definition
      - name: Deploy Step Functions
        uses: ./action/deploy-stepfunctions           # Ferry SF deploy composite action
        with:
          resource-name: ${{ matrix.name }}            # Logical resource name
          state-machine-name: ${{ matrix.state_machine_name }}  # AWS state machine name
          definition-file: ${{ matrix.definition_file }}        # ASL definition file name
          source-dir: ${{ matrix.source }}             # Directory containing the definition
          trigger-sha: ${{ matrix.trigger_sha }}       # Git SHA that triggered the deploy
          deployment-tag: ${{ matrix.deployment_tag }} # Deployment tag (e.g., pr-42)
          aws-role-arn: ${{ secrets.AWS_ROLE_ARN }}    # IAM role for OIDC auth
          aws-region: us-east-1                        # AWS region (adjust as needed)
```

## Variable Substitution

Ferry performs variable substitution on your ASL definition file before deploying. The following variables are replaced at deployment time:

| Variable         | Replaced With                    |
|------------------|----------------------------------|
| `${ACCOUNT_ID}`  | The AWS account ID (from STS)    |
| `${AWS_REGION}`  | The configured AWS region         |

This allows you to write portable definitions without hardcoding account-specific values:

```json
{
  "StartAt": "ProcessOrder",
  "States": {
    "ProcessOrder": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:order-processor",
      "End": true
    }
  }
}
```

Only `${ACCOUNT_ID}` and `${AWS_REGION}` are supported. Other `${...}` patterns (such as JSONPath expressions like `$.input`) are left untouched.

## Content-Hash Skip Detection

Ferry computes a SHA-256 hash of the substituted definition and stores it as a tag on the state machine (`ferry:content-hash`). On subsequent deployments, if the content hash matches the existing tag, the deployment is skipped. This avoids unnecessary state machine version publications when the definition has not actually changed.
