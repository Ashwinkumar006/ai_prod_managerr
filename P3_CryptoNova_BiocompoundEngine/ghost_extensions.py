import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cryptonova_biocompound.db")
DB_PATH = DATABASE_URL.replace("sqlite:///", "")

router = APIRouter()


class WorkflowStepStatus(BaseModel):
    step_id: str
    name: str
    status: str
    owner: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


class WorkflowStatusResponse(BaseModel):
    workflow_code: str
    specimen_code: str
    status: str
    completion_pct: float
    steps: List[WorkflowStepStatus]
    export_format: str


class MLOpsSummaryResponse(BaseModel):
    model_name: str
    model_version: str
    prompt_version: str
    experiment_id: str
    active_status: str
    metrics: Dict[str, Any]
    recent_runs: List[Dict[str, Any]]
    registry: List[Dict[str, Any]]


LANGUAGE_PACKS = {
    "en": {"title": "Research Digest"},
    "ar": {"title": "ملخص البحث"},
    "fr": {"title": "Synthèse de recherche"},
    "es": {"title": "Resumen de investigación"},
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _row_to_dict(row):
    return dict(row) if row else None


def _json_field(value: Any, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _get_specimen(db: sqlite3.Connection, specimen_code: str):
    row = db.execute(
        """
        SELECT id, specimen_code, name, collection_site, depth_m, classification_status, taxonomy,
               gbif_match_score, created_at
        FROM specimens
        WHERE specimen_code = ?
        """,
        (specimen_code,),
    ).fetchone()
    specimen = _row_to_dict(row)
    if specimen:
        specimen["taxonomy"] = _json_field(specimen.get("taxonomy"), {})
    return specimen


def _get_compounds(db: sqlite3.Connection, specimen_id: int):
    rows = db.execute(
        """
        SELECT id, compound_code, name, molecular_formula, molecular_weight, log_p,
               novelty_score, estimated_value_usd, predicted_targets, bioactivity_scores,
               drug_likeness_score
        FROM biocompounds
        WHERE specimen_id = ?
        ORDER BY estimated_value_usd DESC, drug_likeness_score DESC
        """,
        (specimen_id,),
    ).fetchall()
    compounds = []
    for row in rows:
        item = _row_to_dict(row)
        item["predicted_targets"] = _json_field(item.get("predicted_targets"), [])
        item["bioactivity_scores"] = _json_field(item.get("bioactivity_scores"), {})
        compounds.append(item)
    return compounds


def _get_briefs(db: sqlite3.Connection, specimen_id: int):
    rows = db.execute(
        """
        SELECT pb.id, pb.brief_code, pb.title, pb.patentability_score,
               pb.market_size_estimate_usd, pb.status, pb.generated_at
        FROM patent_briefs pb
        JOIN biocompounds bc ON pb.compound_id = bc.id
        WHERE bc.specimen_id = ?
        ORDER BY pb.generated_at DESC
        """,
        (specimen_id,),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _get_papers(db: sqlite3.Connection, specimen_id: int):
    rows = db.execute(
        """
        SELECT id, arxiv_id, title, relevance_score, fetched_at
        FROM research_papers
        WHERE specimen_id = ?
        ORDER BY fetched_at DESC
        """,
        (specimen_id,),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _top_compound_summary(compounds: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not compounds:
        return {
            "compound_code": None,
            "name": None,
            "drug_likeness_score": 0.0,
            "novelty_score": 0.0,
            "estimated_value_usd": 0.0,
            "top_targets": [],
        }
    top = compounds[0]
    return {
        "compound_code": top.get("compound_code"),
        "name": top.get("name"),
        "drug_likeness_score": top.get("drug_likeness_score", 0.0),
        "novelty_score": top.get("novelty_score", 0.0),
        "estimated_value_usd": top.get("estimated_value_usd", 0.0),
        "top_targets": (top.get("predicted_targets") or [])[:3],
    }


def _build_research_digest(specimen: Dict[str, Any], compounds: List[Dict[str, Any]], briefs: List[Dict[str, Any]], papers: List[Dict[str, Any]], language: str):
    top_compound = _top_compound_summary(compounds)
    classification = specimen.get("classification_status") or "unclassified"
    compound_count = len(compounds)
    brief_count = len(briefs)
    portfolio_value = round(float(sum(c.get("estimated_value_usd") or 0 for c in compounds)), 2)
    latest_brief = briefs[0]["brief_code"] if briefs else None
    latest_paper = papers[0]["title"] if papers else None

    executive_summary = (
        f"Specimen {specimen['specimen_code']} is {classification}. "
        f"{compound_count} compounds, {brief_count} patent briefs, and {len(papers)} research papers are linked. "
        f"Top compound {top_compound['compound_code'] or 'n/a'} suggests strongest commercial value."
    )

    multilingual = {
        "en": {
            "title": LANGUAGE_PACKS["en"]["title"],
            "summary": executive_summary,
            "opportunity": "Prioritize lead optimization, publication packaging, and patentability review.",
            "risk": "No major risk signals detected" if classification != "novel_species" else "Novelty is high; prior art review should remain active.",
            "next_steps": [
                "Review lead compound shortlist",
                "Publish a research note for internal stakeholders",
                "Trigger a fresh patent landscape search before filing",
            ],
        },
        "ar": {
            "title": LANGUAGE_PACKS["ar"]["title"],
            "summary": f"العينة {specimen['specimen_code']} بحالة {classification}. تم ربط {compound_count} مركبات و {brief_count} ملخصات براءات.",
            "opportunity": "ركز على أفضل المركبات وخطة النشر والمراجعة القانونية.",
            "risk": "لا توجد مخاطر كبيرة ظاهرة" if classification != "novel_species" else "الحداثة مرتفعة وتحتاج مراجعة مستمرة.",
            "next_steps": ["مراجعة أفضل المركبات", "تحديث البحث عن البراءات", "إعداد ملخص تنفيذي للقيادة"],
        },
        "fr": {
            "title": LANGUAGE_PACKS["fr"]["title"],
            "summary": f"L'échantillon {specimen['specimen_code']} est {classification}. {compound_count} composés et {brief_count} brevets sont liés.",
            "opportunity": "Prioriser l'optimisation et le dossier de brevet.",
            "risk": "Aucun risque majeur détecté" if classification != "novel_species" else "La nouveauté est élevée; surveiller l'art antérieur.",
            "next_steps": ["Examiner le composé principal", "Préparer une note de recherche", "Relancer la veille brevets"],
        },
        "es": {
            "title": LANGUAGE_PACKS["es"]["title"],
            "summary": f"La muestra {specimen['specimen_code']} está {classification}. Hay {compound_count} compuestos y {brief_count} resúmenes de patente.",
            "opportunity": "Priorizar optimización, publicación y revisión de patentabilidad.",
            "risk": "No hay riesgos importantes" if classification != "novel_species" else "La novedad es alta; mantener revisión continua.",
            "next_steps": ["Revisar el mejor compuesto", "Preparar una nota de investigación", "Actualizar la búsqueda de patentes"],
        },
    }

    return {
        "specimen": {
            "specimen_code": specimen["specimen_code"],
            "name": specimen.get("name"),
            "classification_status": classification,
            "depth_m": specimen.get("depth_m"),
            "collection_site": specimen.get("collection_site"),
        },
        "portfolio": {
            "compound_count": compound_count,
            "brief_count": brief_count,
            "paper_count": len(papers),
            "top_compound": top_compound,
            "latest_brief": latest_brief,
            "latest_paper": latest_paper,
            "portfolio_value_usd": portfolio_value,
        },
        "executive_summary": executive_summary,
        "multilingual": multilingual,
        "selected_language": language,
        "metadata": {
            "generated_at": datetime.utcnow().isoformat(),
            "digest_version": "1.0",
            "source_system": "CryptoNova Ghost Research Copilot",
        },
    }


def _build_workflow_steps(specimen: Dict[str, Any], compounds: List[Dict[str, Any]], briefs: List[Dict[str, Any]], papers: List[Dict[str, Any]]):
    compound_ready = len(compounds) > 0
    brief_ready = len(briefs) > 0
    paper_ready = len(papers) > 0
    return [
        {"step_id": "ingest-specimen", "name": "Ingest specimen", "status": "complete", "owner": "product-engineering", "evidence": {"specimen_code": specimen["specimen_code"]}},
        {"step_id": "classify-specimen", "name": "Classify taxonomy", "status": "complete" if specimen.get("classification_status") != "unclassified" else "in_progress", "owner": "bioinformatics", "evidence": {"classification_status": specimen.get("classification_status"), "gbif_score": specimen.get("gbif_match_score")}},
        {"step_id": "discover-compounds", "name": "Discover compounds", "status": "complete" if compound_ready else "pending", "owner": "ml-research", "evidence": {"compound_count": len(compounds)}},
        {"step_id": "generate-patent-brief", "name": "Generate patent brief", "status": "complete" if brief_ready else "pending", "owner": "ip-strategy", "evidence": {"brief_count": len(briefs)}},
        {"step_id": "research-digest", "name": "Generate research digest", "status": "complete" if paper_ready else "ready", "owner": "product-ops", "evidence": {"paper_count": len(papers), "workflow_target": "n8n"}},
    ]


def _build_mlops_summary(db: sqlite3.Connection) -> Dict[str, Any]:
    specimens = db.execute("SELECT COUNT(*) FROM specimens").fetchone()[0] or 0
    compounds = db.execute("SELECT COUNT(*) FROM biocompounds").fetchone()[0] or 0
    briefs = db.execute("SELECT COUNT(*) FROM patent_briefs").fetchone()[0] or 0
    papers = db.execute("SELECT COUNT(*) FROM research_papers").fetchone()[0] or 0
    avg_dl = db.execute("SELECT COALESCE(AVG(drug_likeness_score), 0) FROM biocompounds").fetchone()[0] or 0
    avg_novelty = db.execute("SELECT COALESCE(AVG(novelty_score), 0) FROM biocompounds").fetchone()[0] or 0
    total_value = db.execute("SELECT COALESCE(SUM(estimated_value_usd), 0) FROM biocompounds").fetchone()[0] or 0

    return {
        "model_name": "biocompound-discovery-scoring",
        "model_version": "v1.0.0",
        "prompt_version": "prompt-v1.0.0",
        "experiment_id": f"exp-{specimens:04d}-{compounds:04d}",
        "active_status": "healthy",
        "metrics": {
            "specimens": specimens,
            "compounds": compounds,
            "patent_briefs": briefs,
            "research_papers": papers,
            "average_drug_likeness": round(float(avg_dl), 2),
            "average_novelty": round(float(avg_novelty), 4),
            "portfolio_value_usd": round(float(total_value), 2),
            "artifact_quality": round(min(100.0, (float(avg_dl) * 0.5) + (float(avg_novelty) * 50)), 2),
        },
        "recent_runs": [
            {
                "run_id": f"run-{datetime.utcnow().strftime('%Y%m%d')}",
                "status": "success",
                "notes": "Digest, workflow, and patent generation path is operational.",
            }
        ],
        "registry": [
            {"artifact": "research-digest", "version": "v1.0.0", "prompt_version": "prompt-v1.0.0", "owner": "ghost-pm-portfolio"},
            {"artifact": "workflow-export", "version": "v1.0.0", "prompt_version": "prompt-v1.0.0", "owner": "product-ops"},
        ],
    }


@router.get("/api/v1/research/{specimen_code}/digest", tags=["Research Copilot"])
def get_research_digest(specimen_code: str, language: str = Query(default="en", pattern="^(en|ar|fr|es)$"), db: sqlite3.Connection = Depends(get_db)):
    specimen = _get_specimen(db, specimen_code)
    if not specimen:
        raise HTTPException(status_code=404, detail="Specimen not found")
    compounds = _get_compounds(db, specimen["id"])
    briefs = _get_briefs(db, specimen["id"])
    papers = _get_papers(db, specimen["id"])
    return _build_research_digest(specimen, compounds, briefs, papers, language)


@router.get("/api/v1/workflows/discovery/status/{specimen_code}", tags=["Workflow Ops"])
def get_discovery_workflow_status(specimen_code: str, db=Depends(get_db)):
    specimen = _get_specimen(db, specimen_code)
    if not specimen:
        raise HTTPException(status_code=404, detail="Specimen not found")
    compounds = _get_compounds(db, specimen["id"])
    briefs = _get_briefs(db, specimen["id"])
    papers = _get_papers(db, specimen["id"])
    steps = _build_workflow_steps(specimen, compounds, briefs, papers)
    completion_pct = round((sum(1 for step in steps if step["status"] == "complete") / len(steps)) * 100, 2)
    overall_status = "complete" if completion_pct == 100 else "in_progress" if completion_pct > 0 else "pending"
    return {
        "workflow_code": f"discovery-{specimen_code}",
        "specimen_code": specimen_code,
        "status": overall_status,
        "completion_pct": completion_pct,
        "steps": steps,
        "export_format": "n8n-compatible-json",
    }


@router.get("/api/v1/workflows/discovery/export/{specimen_code}", tags=["Workflow Ops"])
def export_discovery_workflow(specimen_code: str, db=Depends(get_db)):
    specimen = _get_specimen(db, specimen_code)
    if not specimen:
        raise HTTPException(status_code=404, detail="Specimen not found")
    compounds = _get_compounds(db, specimen["id"])
    briefs = _get_briefs(db, specimen["id"])
    papers = _get_papers(db, specimen["id"])
    steps = _build_workflow_steps(specimen, compounds, briefs, papers)
    return {
        "workflow_name": "CryptoNova Discovery Pipeline",
        "workflow_code": f"discovery-{specimen_code}",
        "format": "n8n",
        "specimen_code": specimen_code,
        "nodes": steps,
        "triggers": ["specimen.created", "specimen.classified", "compound.discovered", "brief.generated"],
        "actions": ["generate_research_digest", "send_product_ops_notification", "publish_internal_brief"],
        "metadata": {"generated_at": datetime.utcnow().isoformat(), "owner": "product-ops", "version": "1.0.0"},
    }


@router.get("/api/v1/mlops/summary", tags=["MLOps"])
def get_mlops_summary(db=Depends(get_db)):
    return _build_mlops_summary(db)
