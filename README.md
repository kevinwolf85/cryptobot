# CryptoBot (Paper Trading)

Initial implementation of a crypto paper-trading bot using:
- MACD crossover signals
- Buy/sell volume ratio monitoring
- Local web dashboard
- AWS CLI-friendly deployment scripts (no CDK required)

Live trading is disabled by default and intentionally not implemented.

## Features
- Standard-library Python backend (`python3` only)
- Binance public market data integration
- Paper account state persisted to JSON
- Trading engine loop with manual tick endpoint
- Minimal dashboard (`/`) + API endpoints (`/api/*`)
- Unit tests using `unittest`

## Project Layout
- `cryptobot/`: backend package and static dashboard assets
- `tests/`: unit tests
- `scripts/aws/`: shell scripts for packaging + EC2 deployment
- `docs/`: issue backlog and operational runbook

## Quick Start (Local)
1. `cd /Users/kevinwolf/cryptobot`
2. `cp .env.example .env`
3. `python3 -m cryptobot.main`
4. Open `http://127.0.0.1:8080`

## Environment Settings
See `.env.example`. Key values:
- `LIVE_TRADING_ENABLED=false` (must remain false)
- `MARKET_DATA_BASE_URL=https://api.binance.us`
- `TRADE_USD_SIZE=50`
- `VOLUME_RATIO_THRESHOLD=1.2`
- `PAPER_STATE_FILE=state/paper_account.json`

## Run Tests
```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## API Endpoints
- `GET /api/status`: bot/account status, last signal, error state
- `GET /api/trades`: executed paper trades
- `GET /api/config`: effective config view
- `POST /api/tick`: run strategy loop once immediately

## AWS Deployment Notes
AWS deploy is CLI-first and includes one-command provisioning.

One-command deploy:
```sh
cd /Users/kevinwolf/cryptobot
bash scripts/aws/deploy_oneclick.sh
```

Optional variables:
- `AWS_PROFILE` (default `default`)
- `AWS_REGION` (default `us-east-1`)
- `INSTANCE_TYPE` (default `t3.micro`)
- `APP_NAME` (default `cryptobot-paper`)

Manual scripts are still available:
1. `scripts/aws/package_and_upload.sh`
2. `scripts/aws/create_infra.sh`
3. `scripts/aws/deploy_ec2.sh`

## Safety
- This project is paper trading only.
- Live execution path is not implemented.
- If live mode is enabled, the app exits immediately to prevent accidental trading.
- One-click EC2 deployment opens only port `8080` and does not add SSH ingress.
