# Removal — the protocol that leaves nothing billing

*Written for the AI assistant. When your human says any version of
"remove it all", run this protocol. It is designed so that at the end
you can truthfully say: nothing of this deployment is still charging
you.*

## 1. Confirm intent (once, plainly)

"This permanently removes the instance, the agent's entire evolved
mind, its trading history, and the interface. Positions in the Alpaca
account are NOT automatically closed. Do you want me to (a) export the
agent's brain first, and (b) close any open positions first?"

## 2. (Offered) Export the brain — the only thing worth keeping

```bash
IID=$(aws cloudformation describe-stacks --stack-name alpaca-mind \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
aws ssm send-command --instance-ids $IID --document-name AWS-RunShellScript \
  --parameters commands='tar czf /tmp/mind-brain.tar.gz -C /srv/mind workspace ledger.db logs && ls -la /tmp/mind-brain.tar.gz'
# copy it somewhere the human owns (their S3 bucket, or start-session + base64 for small brains)
```
The tarball is the complete mind: identity, evolved doctrine, journal,
memory, ledger, every transcript. A future deployment can be restored
from it (OPERATIONS.md).

## 3. (Offered) Close open positions

If yes: `HALT` first, then close each open position via the trade CLI
as the `mind` user, then `trade reconcile` to confirm flat. (Paper
accounts: closing is optional — simulated positions cost nothing.)

## 4. Empty the backup bucket, then delete the stack

S3 refuses to delete a non-empty bucket, so the nightly-backup bucket
is emptied first (offer to copy the newest backup somewhere the human
owns before this — it is a complete restorable mind):

```bash
B=$(aws cloudformation describe-stacks --stack-name alpaca-mind \
  --query "Stacks[0].Outputs[?OutputKey=='BackupBucketName'].OutputValue" --output text)
aws s3 rm "s3://$B" --recursive
aws cloudformation delete-stack --stack-name alpaca-mind
aws cloudformation wait stack-delete-complete --stack-name alpaca-mind
```
Every resource carries delete-on-removal by design: instance, volume,
VPC, security group, IAM role, backup bucket, EIP if one was allocated.

## 5. Delete the secrets (SSM parameters survive stacks on purpose)

```bash
P=/alpaca-mind
aws ssm delete-parameters --names \
  $P/ALPACA_API_KEY $P/ALPACA_SECRET_KEY $P/ALPACA_PAPER \
  $P/CLAUDE_CODE_OAUTH_TOKEN $P/UI_PASSWORD
```

## 6. Verify zero residue, then say so

```bash
aws cloudformation describe-stacks --stack-name alpaca-mind 2>&1 | grep -q "does not exist" && echo "stack: gone"
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=aws:cloudformation:stack-name,Values=alpaca-mind \
  --query 'ResourceTagMappingList[].ResourceARN'      # expect: []
```

Close with the truth: "Everything this deployment created in AWS is
gone and nothing is still billing. Your Claude and Alpaca subscriptions
are yours directly — cancel those with the providers if you're done
with them too. Your exported brain is at <wherever step 2 put it>."
