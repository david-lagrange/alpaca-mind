# Teardown

Total removal is a design goal of this stack: one delete, no residue.

```
aws cloudformation delete-stack --stack-name <stack-name>
aws cloudformation wait stack-delete-complete --stack-name <stack-name>
```

## What the delete removes

Everything the stack created — every resource carries `DeletionPolicy: Delete`:

- EC2 instance, including its root EBS volume (`DeleteOnTermination: true`;
  no snapshots are ever taken)
- Elastic IP, if `AllocateElasticIp` was enabled
- Security group
- IAM role, inline policy, and instance profile
- VPC, subnet, internet gateway, route table, and associations

The stack creates no S3 buckets, no snapshots, no log groups, and no other
storage — there is nothing to retain.

## What the delete does NOT remove (by design)

The SSM SecureString parameters under your prefix (default `/alpaca-mind`).
You created them before the stack, so they outlive it — convenient for
redeploys. To remove them too:

```
aws ssm delete-parameters --names \
  /alpaca-mind/ALPACA_API_KEY \
  /alpaca-mind/ALPACA_SECRET_KEY \
  /alpaca-mind/ALPACA_PAPER \
  /alpaca-mind/CLAUDE_CODE_OAUTH_TOKEN \
  /alpaca-mind/UI_PASSWORD
```

## Residue check

None is expected. To verify, query for anything still tagged with the stack
(CloudFormation tags every resource it creates with the stack name):

```
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=aws:cloudformation:stack-name,Values=<stack-name> \
  --query 'ResourceTagMappingList[].ResourceARN'
```

An empty list means the account is clean. Note that agent state (workspaces,
ledger, logs) lived only on the instance's root volume — deleting the stack
destroys it permanently, so export anything you want to keep first.
