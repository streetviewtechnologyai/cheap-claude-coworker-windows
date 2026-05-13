# Diagnose why the Token Monitor's "Claude 5h / 7d" rows are falling back to
# token counts instead of showing percentages + reset times.
#
# Run from a REGULAR PowerShell window (NOT Claude Code Desktop's terminal):
#   powershell -ExecutionPolicy Bypass -File .\install\diagnose_quota.ps1

$VenvPy = Join-Path $env:LOCALAPPDATA "claude-coworker\venv\Scripts\python.exe"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Set-Location $RepoRoot

& $VenvPy -c @"
import json, pathlib, os, sys
sys.path.insert(0, r'$RepoRoot')
from monitor.sources import claude_quota as cq

print('CLI credentials path:', cq.CREDENTIALS_PATH)
print('  exists:', cq.CREDENTIALS_PATH.exists())
print('Desktop search dirs:')
for d in cq._desktop_search_dirs():
    print(f'  {d}  exists={d.exists()}')
print('Resolved config: ', cq.DESKTOP_CONFIG_PATH, ' exists=', cq.DESKTOP_CONFIG_PATH.exists())
print('Resolved LS:     ', cq.DESKTOP_LOCAL_STATE_PATH, ' exists=', cq.DESKTOP_LOCAL_STATE_PATH.exists())

tok = cq._bearer()
print('bearer found:', bool(tok), 'length:', len(tok) if tok else 0)
if not tok:
    print('-> no bearer; quota row will fall back to token count')
    sys.exit(0)

print()
print('Trying GET /api/oauth/usage ...')
import requests
try:
    r = requests.get(cq.USAGE_URL,
        headers={'Authorization': f'Bearer {tok}', 'anthropic-beta': 'oauth-2025-04-20'},
        timeout=5)
    print('  status:', r.status_code)
    if r.status_code == 200:
        print('  body:', r.text[:500])
    else:
        print('  body:', r.text[:300])
except Exception as e:
    print('  EXC:', type(e).__name__, e)

print()
print('Trying POST /v1/messages (just to read headers) ...')
for model in cq.MODEL_FALLBACKS:
    print(' model=', model)
    try:
        r = requests.post(cq.MESSAGES_URL,
            headers={
                'Authorization': f'Bearer {tok}',
                'anthropic-version': '2023-06-01',
                'anthropic-beta': 'oauth-2025-04-20',
                'Content-Type': 'application/json',
            },
            json={'model': model, 'max_tokens': 1, 'messages': [{'role':'user','content':'.'}]},
            timeout=10)
        print('   status:', r.status_code)
        for k,v in r.headers.items():
            if 'ratelimit' in k.lower() or 'unified' in k.lower():
                print(f'   {k}: {v}')
        if r.status_code not in (200, 429):
            print('   body:', r.text[:300])
    except Exception as e:
        print('   EXC:', type(e).__name__, e)

print()
print('Final fetch() result:')
q = cq.fetch()
print(' ', q)
"@
