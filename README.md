# AI Product Manager Portfolio Bundle

This repository is a portfolio bundle of four distinct AI-first product concepts, each implemented as a working FastAPI application with its own domain model, workflows, and Ghost-focused feature slice.

The repo is designed to show:

- product strategy translated into software
- practical AI and workflow automation
- thoughtful feature prioritization
- strong API-first system design
- differentiated case-study positioning across multiple products

## Portfolio Structure

| Project | Positioning | Core Story | Ghost-Relevant Slice | Port |
|---|---|---|---|---|
| `P1_AstroMarine_CascadeFailureEngine` | AI operations + autonomous decision support | Cascade risk modeling for hybrid infrastructure | Operator copilot, multilingual incident briefings, replay timelines, ops summaries | `8001` |
| `P2_PolarSynth_SovereigntyPlatform` | AI research and publishing intelligence platform | Strategic sovereignty and resource intelligence | Executive intelligence briefs, multilingual outputs, video/storyboard payloads, workflow exports | `8002` |
| `P3_CryptoNova_BiocompoundEngine` | AI discovery workflow with experimentation discipline | Biocompound discovery and patent pipeline | Research digests, workflow status, lightweight MLOps summary | `8003` |
| `P4_DeepGenome_GeneticMarketplace` | AI-enabled compliance and commercialization platform | Genetic IP licensing, compliance, and royalties | Compliance explainer, multilingual summaries, workflow templates, ops/risk reporting | `8004` |

## Why This Repo Exists

This bundle was optimized as a product-management portfolio rather than a generic engineering repo.

The goal was not to add every possible AI buzzword. The goal was to demonstrate:

- where AI helps users make decisions faster
- where workflow automation creates leverage for small teams
- where multilingual or executive-ready outputs matter
- where governance, auditability, and operational thinking improve the product

## What Was Added In This Pass

### Shared direction

Across the portfolio, the work emphasizes:

- AI-assisted output generation
- API-first workflow surfaces
- product-facing operational metadata
- demoable, high-signal endpoints
- portfolio-ready differentiation between products

### Product-specific upgrades

#### P1 AstroMarine

- multilingual incident briefing generation
- replay timeline for telemetry and cascade events
- ops summary endpoint with prompt/template metadata

Key endpoints:

- `POST /api/v1/missions/{mission_code}/copilot/briefing`
- `GET /api/v1/missions/{mission_code}/timeline/replay`
- `GET /api/v1/missions/{mission_code}/ops/summary`

#### P2 PolarSynth

- strategic intelligence briefing generation
- multilingual briefing output
- executive video brief/storyboard payload
- n8n-ready workflow export for briefing automation

Key endpoints:

- `POST /api/v1/zones/{zone_code}/briefings/generate`
- `GET /api/v1/zones/{zone_code}/briefings`
- `GET /api/v1/zones/{zone_code}/briefings/{briefing_code}`
- `GET /api/v1/zones/{zone_code}/briefings/{briefing_code}/video`
- `GET /api/v1/zones/{zone_code}/workflows/briefing-template`

#### P3 CryptoNova

- multilingual research digest generation
- agentic workflow status summary for discovery stages
- lightweight MLOps summary surface for portfolio governance

Key endpoints:

- `POST /api/v1/research/digest`
- `GET /api/v1/specimens/{specimen_code}/workflow-status`
- `GET /api/v1/mlops/summary`

#### P4 DeepGenome

- human-readable compliance explainer
- multilingual marketplace/compliance summary
- n8n-ready workflow templates for licensing and royalties
- ops/risk summary surface

Key endpoints:

- `POST /api/v1/compliance/brief`
- `GET /api/v1/compliance/summary`
- `GET /api/v1/workflows/templates`
- `GET /api/v1/workflows/templates/{workflow_id}`
- `GET /api/v1/ops/risk-summary`

## How To Run

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-project.ps1 p1
```

Project keys:

- `p1` -> AstroMarine on `8001`
- `p2` -> PolarSynth on `8002`
- `p3` -> CryptoNova on `8003`
- `p4` -> DeepGenome on `8004`

Optional reload mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-project.ps1 p3 -Reload
```

## Repository Notes

- Each project is intentionally self-contained.
- Each project has its own `main.py`, `enterprise_core.py`, and `requirements.txt`.
- The root `run-project.ps1` script standardizes local startup.
- The root `.gitignore` excludes local virtualenvs, temporary tooling, logs, and database files.

## Verification Status

This repo has been verified at multiple levels during the build pass:

- all four projects compile with `python -m py_compile`
- P1 operator copilot routes were exercised end-to-end
- P4 compliance/workflow routes were exercised end-to-end
- P2 and P3 feature slices were implemented and compile cleanly

## Best Way To Read This Portfolio

If you are reviewing this as a hiring manager or product leader:

1. Start with `P2` and `P4` for the clearest publishing, workflow, and product-judgment signals.
2. Review `P1` for systems thinking, AI-assisted operations, and decision support.
3. Review `P3` for AI/ML product maturity, research workflow design, and experimentation framing.

## Submission Framing

This bundle is best presented as:

- 4 flagship products showing breadth of product thinking
- 4 complementary case studies showing judgment and prioritization
- 1 portfolio system showing practical AI, workflow automation, and execution discipline

## License / Intent

This repository is being used as a portfolio and product strategy showcase.
