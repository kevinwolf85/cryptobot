# Deployment Report

Date: 2026-02-19  
Region: `us-east-1`  
Account: `275755767242`

## Deployed Resources
- EC2 instance: `i-05d2315e11ca7a298`
- Public URL: `http://44.223.87.17:8080`
- S3 bucket: `cryptobot-paper-275755767242-us-east-1`
- Security group: `sg-0af6eadc274c23aea`
- IAM instance profile: `cryptobot-paper-instance-profile`

## Validation Performed
1. Unit tests passed locally:
   - `python3 -m unittest discover -s tests -p 'test_*.py' -v`
2. Live API health check:
   - `GET /api/status` returned JSON with `last_error: null`
3. Chrome DevTools validation against deployed URL:
   - Dashboard loaded successfully
   - `GET /api/status` and `GET /api/trades` returned `200`
   - `POST /api/tick` returned `200` and dashboard updated

## Issues Found and Addressed
1. Free-tier deploy mismatch:
   - `t4g.nano` failed with free-tier eligibility in this account.
   - Fixed default to `t3.micro` and architecture-aware AMI resolution.
2. macOS packaging bug:
   - `mktemp` template with `.tar.gz` suffix caused collisions.
   - Fixed by generating temp base name then appending suffix.
3. Python runtime compatibility:
   - EC2 Python `3.9` failed on `datetime.UTC` and `|` annotation evaluation.
   - Fixed by using `timezone.utc` and `from __future__ import annotations`.

## Remaining Non-blocking Item
1. Browser requests `favicon.ico` and gets `404`.
   - Does not affect bot logic or API behavior.

## Cleanup Command
```sh
aws ec2 terminate-instances --profile default --region us-east-1 --instance-ids i-05d2315e11ca7a298
```
