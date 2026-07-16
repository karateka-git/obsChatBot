$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

docker compose build catcher
docker compose run --rm catcher python -m obs_chat_bot --healthcheck
