# Facts — this deployment's standing coordinates

*Copy to `audits-local/FACTS.md` on first run; re-resolve after any
stack change. Everything the books need to reach the machine and
judge it lives here — never in the public books.*

| Fact | Value | Re-resolve with |
|---|---|---|
| Stack name / region | | |
| Instance id | | `aws cloudformation describe-stacks --stack-name <stack> --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text` |
| Public address / domain (and whether TLS is configured) | | outputs key `PublicIp` |
| Backup bucket | | outputs key `BackupBucketName` |
| SSM prefix | | |
| Stack parameters in force (repeat all on every deploy) | | |
| Repository and branch; on-box clone path | | |
| Site auth mode (password-only or showcase) | | |
| Units in play | | `systemctl is-active …` |
| CLI pin (both users) | | `sudo -u mind -H claude --version` |
| Models in force (per config) | | the engine's config copies |
| Mission (one line) | | |
| Benchmark (chosen at baseline; changes only with an epoch line) | | |
| Seat / plan tier (for you; never messaged to the mind); the result subtype a limit wait produces, once observed | | |
| Owner's risk line, if set (SECURITY.md live-money section): the equity or drawdown at which you HALT and call your human | | |

## Dated watch rows (platform register)
Rows the platform playbook re-checks every pass: the current model
lineup and last-verified release; any vendor-data finding the mind
routes around; the MCP server's last-known release; anything else the
register told you to watch.

| Row | Fact | Last verified | Next check |
|---|---|---|---|

## Epoch lines
Dates that split evolution windows: birth, owner notes, engine
changes, model boundaries, declared event windows.

| Date | Epoch | Why it splits the window |
|---|---|---|
