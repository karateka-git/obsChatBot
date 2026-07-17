$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

docker compose build tg_catcher
docker compose run --rm tg_catcher python -m obs_chat_bot --healthcheck
docker compose run --rm tg_catcher python -m obs_chat_bot --sqlite-smoke
docker compose run --rm tg_catcher python -m obs_chat_bot --pipeline-smoke
docker compose run --rm tg_catcher python -m obs_chat_bot --analysis-smoke
