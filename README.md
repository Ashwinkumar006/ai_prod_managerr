# ai_prod_managerr
productmanager

## Run A Project

From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-project.ps1 p1
```

Available project keys:

- `p1` -> AstroMarine on port `8001`
- `p2` -> PolarSynth on port `8002`
- `p3` -> CryptoNova on port `8003`
- `p4` -> DeepGenome on port `8004`

Optional reload mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-project.ps1 p3 -Reload
```

## Ghost PM Feature Slices

- `P1` adds an operator copilot slice with multilingual incident briefings, replay timelines, and ops summaries.
- `P2` adds executive intelligence briefings, video/storyboard payloads, and n8n-ready workflow exports.
- `P3` adds research digests, workflow status tracking, and a lightweight MLOps summary surface.
- `P4` adds compliance explainers, multilingual compliance summaries, workflow templates, and ops/risk reporting.
