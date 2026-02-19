# Issue Backlog and Status

## Resolved in this iteration
1. Deployment script had AMI/instance architecture mismatch risk. Fixed by automatic AMI selection based on instance type.
2. Deployment required manual VPC/subnet/key/profile setup. Added `scripts/aws/deploy_oneclick.sh` for safer zero-touch provisioning in default VPC.
3. One-click deployment now avoids opening SSH (`22`) ingress and only opens app port `8080`.
4. One-click deployment now defaults to free-tier-friendly `t3.micro`.
5. Fixed macOS `mktemp` collision issue in packaging/deploy scripts.
6. Fixed Python runtime compatibility for AWS AMI Python 3.9.

## Open issues
1. Add exchange abstraction for multiple providers (Binance, Coinbase, Kraken).
2. Add persistence for price/signal history to support charting.
3. Add authentication to dashboard endpoints before internet exposure.
4. Add integration tests for API endpoints and market data retries.
5. Add systemd service file for managed EC2 startup/restart.
6. Add optional webhook notifications for buy/sell events.
7. Add configurable stop-loss and max-daily-loss guard rails.
8. Add CI (lint + tests) once repository hosting is configured.
9. Add a favicon asset to remove dashboard `favicon.ico` 404 noise.
