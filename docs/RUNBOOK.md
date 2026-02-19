# CryptoBot Runbook (Paper Trading)

## Start Locally
1. `cd /Users/kevinwolf/cryptobot`
2. `cp .env.example .env`
3. `python3 -m cryptobot.main`
4. Open `http://127.0.0.1:8080`

## Health Checks
1. `curl -s http://127.0.0.1:8080/api/status | python3 -m json.tool`
2. Confirm `live_trading_enabled` is `false`.
3. Confirm `last_error` is `null` or troubleshoot connectivity.

## Force a Single Tick
1. `curl -X POST http://127.0.0.1:8080/api/tick`

## Common Failures
1. Binance API unavailable or restricted: switch `MARKET_DATA_BASE_URL` (default `https://api.binance.us`) and restart.
2. Port in use: set `PORT` in `.env` and restart.
3. Permission denied writing state file: set writable `PAPER_STATE_FILE`.

## Reset Paper Account
1. Stop bot.
2. Delete `state/paper_account.json`.
3. Restart bot to reinitialize with `PAPER_STARTING_CASH`.

## Deploy to AWS (One Command)
1. `cd /Users/kevinwolf/cryptobot`
2. `bash scripts/aws/deploy_oneclick.sh`
3. Open the printed public URL.
4. Verify API health:
   `curl -s http://<public-ip>:8080/api/status | python3 -m json.tool`

## Deploy to AWS (Manual Path)
1. Export required env vars (`AWS_REGION`, networking IDs, `S3_BUCKET`, etc.).
2. `bash scripts/aws/package_and_upload.sh`
3. `bash scripts/aws/create_infra.sh`
4. `bash scripts/aws/deploy_ec2.sh`
5. Verify instance log: `/var/log/cryptobot.log`

## Cleanup
1. `aws ec2 terminate-instances --profile default --region us-east-1 --instance-ids <instance-id>`
2. Remove S3 object or bucket if you are done testing.

## Live Trading Safety
1. Live mode is intentionally unimplemented.
2. If `LIVE_TRADING_ENABLED=true`, app exits with runtime error.
