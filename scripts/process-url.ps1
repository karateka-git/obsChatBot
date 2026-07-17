param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Url
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

docker compose build tg_catcher
docker compose run --rm tg_catcher python -m obs_chat_bot --process-url $Url
