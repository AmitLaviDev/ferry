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

## Terraform Lifecycle

Since Ferry manages the state machine definition at deploy time, your Terraform (or other IaC) should ignore changes to the `definition` and the `ferry:content-hash` tag. Otherwise Terraform will try to revert Ferry's deployments:

```hcl
resource "aws_sfn_state_machine" "example" {
  name     = "my-state-machine"
  role_arn = aws_iam_role.sf_execution.arn

  definition = jsonencode({
    Comment = "Placeholder -- overwritten by Ferry deploy"
    StartAt = "Placeholder"
    States = {
      Placeholder = {
        Type = "Pass"
        End  = true
      }
    }
  })

  lifecycle {
    ignore_changes = [definition, tags["ferry:content-hash"]]
  }
}
```

## Content-Hash Skip Detection

Ferry computes a SHA-256 hash of the substituted definition and stores it as a tag on the state machine (`ferry:content-hash`). On subsequent deployments, if the content hash matches the existing tag, the deployment is skipped. This avoids unnecessary state machine version publications when the definition has not actually changed.
