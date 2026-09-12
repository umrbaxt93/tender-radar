$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python ci/github_review.py @args
exit $LASTEXITCODE
