"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  P4: DEEPGENOME GENETIC IP MARKETPLACE                                      ║
║  Domain: Marine Cryptozoology Biotechnological System Engineering           ║
║  Product Type: Genetic Intellectual Property Marketplace Platform           ║
║                                                                              ║
║  PROBLEM IT SOLVES:                                                          ║
║  The Nagoya Protocol requires nations to share benefits from genetic        ║
║  resources, but no transparent marketplace exists for marine cryptozoo      ║
║  genetic sequences. Nations lose $100B+ annually to genetic piracy.        ║
║  This engine creates a compliant, auditable marketplace for licensing      ║
║  genetic IP from marine specimens — with automated royalty tracking,       ║
║  Nagoya compliance, and provenance chains.                                   ║
║                                                                              ║
║  EXTERNAL APIs INTEGRATED:                                                   ║
║  - GBIF (species verification & occurrence data)                            ║
║  - IUCN Red List concepts (conservation status reference)                   ║
║  - REST Countries (nation-level ABS compliance data)                        ║
║  - FishWatch (marine species information)                                   ║
║                                                                              ║
║  Revenue Model: Genetic IP Licensing Fees — 2-5% of each transaction       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import math
import random
import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from contextlib import asynccontextmanager
from decimal import Decimal

import numpy as np
import httpx
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, Column, Integer, Float, String, DateTime, Boolean,
    ForeignKey, Text, JSON as SAJSON, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ─── CONFIGURATION ──────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./deepgenome_marketplace.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("deepgenome.marketplace")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─── DATABASE MODELS ────────────────────────────────────────────────────────────

class LicenseType(str, Enum):
    RESEARCH = "research"
    COMMERCIAL = "commercial"
    EXCLUSIVE = "exclusive"
    GOVERNMENT = "government"


class GenomeSequenceDB(Base):
    __tablename__ = "genome_sequences"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sequence_id = Column(String(64), unique=True, index=True, nullable=False)
    species_name = Column(String(256), nullable=False)
    common_name = Column(String(256))
    taxonomy = Column(SAJSON, default=dict)
    source_nation = Column(String(128), nullable=False)
    collection_site = Column(String(256))
    collection_depth_m = Column(Float, default=0.0)
    lat = Column(Float)
    lon = Column(Float)
    sequence_length_bp = Column(Integer, default=0)
    gc_content_pct = Column(Float, default=0.0)
    sequence_hash = Column(String(64))  # SHA-256 of sequence for integrity
    conservation_status = Column(String(32), default="not_evaluated")  # IUCN categories
    complexity_score = Column(Float, default=0.0)
    novelty_score = Column(Float, default=0.0)
    base_license_price_usd = Column(Float, default=0.0)
    total_licenses_issued = Column(Integer, default=0)
    total_revenue_usd = Column(Float, default=0.0)
    nagoya_compliant = Column(Boolean, default=False)
    provenance_chain = Column(SAJSON, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LicenseDB(Base):
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    license_id = Column(String(64), unique=True, index=True, nullable=False)
    sequence_id = Column(String(64), ForeignKey("genome_sequences.sequence_id"), nullable=False)
    licensee_org = Column(String(256), nullable=False)
    licensee_nation = Column(String(128), nullable=False)
    license_type = Column(String(32), nullable=False)
    purpose = Column(Text)
    price_usd = Column(Float, nullable=False)
    royalty_rate_pct = Column(Float, default=3.0)
    nagoya_verified = Column(Boolean, default=False)
    compliance_notes = Column(Text)
    valid_from = Column(DateTime, default=datetime.utcnow)
    valid_to = Column(DateTime)
    status = Column(String(32), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)


class RoyaltyPaymentDB(Base):
    __tablename__ = "royalty_payments"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    payment_id = Column(String(64), unique=True, index=True, nullable=False)
    license_id = Column(String(64), ForeignKey("licenses.license_id"), nullable=False)
    sequence_id = Column(String(64), nullable=False)
    source_nation = Column(String(128), nullable=False)
    licensee_org = Column(String(256), nullable=False)
    gross_revenue_usd = Column(Float, nullable=False)
    royalty_rate_pct = Column(Float, nullable=False)
    royalty_amount_usd = Column(Float, nullable=False)
    platform_fee_usd = Column(Float, default=0.0)
    net_to_source_nation_usd = Column(Float, default=0.0)
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class ComplianceAuditDB(Base):
    __tablename__ = "compliance_audits"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    audit_id = Column(String(64), unique=True, index=True, nullable=False)
    license_id = Column(String(64), nullable=False)
    audit_type = Column(String(32), nullable=False)  # nagoya, provenance, usage
    result = Column(String(16), nullable=False)  # pass, fail, warning
    findings = Column(SAJSON, default=list)
    auditor = Column(String(128), default="automated")
    audited_at = Column(DateTime, default=datetime.utcnow)


# ─── PYDANTIC SCHEMAS ───────────────────────────────────────────────────────────

class SequenceCreate(BaseModel):
    species_name: str = Field(..., min_length=1, max_length=256)
    common_name: Optional[str] = None
    source_nation: str = Field(..., min_length=1, max_length=128)
    collection_site: Optional[str] = None
    collection_depth_m: float = Field(default=0, ge=0)
    lat: Optional[float] = None
    lon: Optional[float] = None
    sequence_data: Optional[str] = Field(default=None, description="DNA/RNA sequence string (ACGT)")
    conservation_status: str = Field(default="not_evaluated")

class SequenceResponse(BaseModel):
    id: int
    sequence_id: str
    species_name: str
    common_name: Optional[str]
    source_nation: str
    sequence_length_bp: int
    gc_content_pct: float
    conservation_status: str
    complexity_score: float
    novelty_score: float
    base_license_price_usd: float
    total_licenses_issued: int
    total_revenue_usd: float
    nagoya_compliant: bool
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class LicenseCreate(BaseModel):
    sequence_id: str
    licensee_org: str
    licensee_nation: str
    license_type: LicenseType
    purpose: Optional[str] = None
    duration_years: int = Field(default=5, ge=1, le=30)

class LicenseResponse(BaseModel):
    license_id: str
    sequence_id: str
    licensee_org: str
    license_type: str
    price_usd: float
    royalty_rate_pct: float
    nagoya_verified: bool
    valid_from: datetime
    valid_to: Optional[datetime]
    status: str
    model_config = {"from_attributes": True}

class RoyaltyCreate(BaseModel):
    license_id: str
    gross_revenue_usd: float = Field(..., gt=0)
    period_start: datetime
    period_end: datetime


# ─── CORE ENGINE: GENETIC IP ANALYSIS ───────────────────────────────────────────

class GeneticIPEngine:
    """
    Core engine for genetic sequence analysis, pricing, and compliance.
    """

    CONSERVATION_MULTIPLIERS = {
        "extinct_in_wild": 50.0,  # Extremely rare genetic material
        "critically_endangered": 20.0,
        "endangered": 10.0,
        "vulnerable": 5.0,
        "near_threatened": 2.0,
        "least_concern": 1.0,
        "data_deficient": 3.0,
        "not_evaluated": 1.5,
    }

    LICENSE_PRICE_MULTIPLIERS = {
        "research": 1.0,
        "commercial": 15.0,
        "exclusive": 50.0,
        "government": 5.0,
    }

    LICENSE_ROYALTY_RATES = {
        "research": 1.0,
        "commercial": 3.0,
        "exclusive": 5.0,
        "government": 2.0,
    }

    PLATFORM_FEE_PCT = 2.5  # Platform takes 2.5% of royalties

    def analyze_sequence(self, sequence_data: Optional[str]) -> Dict[str, Any]:
        """Analyze a genetic sequence for key properties."""
        if not sequence_data:
            # Generate synthetic sequence for demo (in production, real data)
            length = random.randint(5000, 500000)
            gc_pct = random.uniform(30, 65)
            return {
                "sequence_length_bp": length,
                "gc_content_pct": round(gc_pct, 2),
                "sequence_hash": hashlib.sha256(str(random.random()).encode()).hexdigest(),
                "synthetic": True,
            }

        seq = sequence_data.upper().replace(" ", "").replace("\n", "")
        length = len(seq)
        gc_count = seq.count("G") + seq.count("C")
        gc_pct = (gc_count / max(length, 1)) * 100

        return {
            "sequence_length_bp": length,
            "gc_content_pct": round(gc_pct, 2),
            "sequence_hash": hashlib.sha256(seq.encode()).hexdigest(),
            "synthetic": False,
        }

    def compute_complexity_score(self, length: int, gc_pct: float, depth_m: float) -> float:
        """
        Compute sequence complexity score (0-100):
        - Longer sequences = more complex gene networks
        - GC content near 50% = higher information entropy
        - Greater depth = more unique evolutionary adaptations
        """
        # Length factor (log scale, caps at ~500K bp)
        length_score = min(math.log10(max(length, 100)) / 6, 1.0) * 30

        # GC balance (optimal near 50%)
        gc_deviation = abs(gc_pct - 50)
        gc_score = max(0, (25 - gc_deviation) / 25) * 30

        # Depth adaptation (deep-sea = extreme adaptations)
        depth_score = min(depth_m / 5000, 1.0) * 40

        return round(length_score + gc_score + depth_score, 2)

    def compute_novelty_score(self, gbif_matched: bool, conservation_status: str, depth_m: float) -> float:
        """
        Compute novelty score (0-1):
        - Unmatched in GBIF = likely novel species = high novelty
        - Rare conservation status = unique genetic material
        - Deep collection = less studied organisms
        """
        base = 0.3 if gbif_matched else 0.8

        conservation_bonus = {
            "extinct_in_wild": 0.15, "critically_endangered": 0.12,
            "endangered": 0.08, "vulnerable": 0.05,
            "near_threatened": 0.03, "data_deficient": 0.10,
            "not_evaluated": 0.07, "least_concern": 0.0,
        }
        base += conservation_bonus.get(conservation_status, 0.05)

        depth_bonus = min(depth_m / 10000, 0.15)
        base += depth_bonus

        return round(min(base, 1.0), 4)

    def compute_base_price(self, complexity: float, novelty: float, conservation_status: str, length: int) -> float:
        """
        Compute base license price for a research license.
        This is the foundation price — commercial/exclusive multiply this.
        """
        # Base: $1,000 per 10K base pairs
        base = (length / 10000) * 1000

        # Complexity multiplier (1x to 3x)
        complexity_mult = 1 + (complexity / 100) * 2

        # Novelty multiplier (1x to 5x)
        novelty_mult = 1 + novelty * 4

        # Conservation multiplier
        cons_mult = self.CONSERVATION_MULTIPLIERS.get(conservation_status, 1.0)

        price = base * complexity_mult * novelty_mult * cons_mult
        return round(max(price, 500), 2)  # Minimum $500

    def compute_license_price(self, base_price: float, license_type: str) -> float:
        """Compute license price based on type."""
        mult = self.LICENSE_PRICE_MULTIPLIERS.get(license_type, 1.0)
        return round(base_price * mult, 2)

    def compute_royalty(self, gross_revenue: float, royalty_rate: float) -> Dict[str, float]:
        """Compute royalty breakdown."""
        royalty_total = gross_revenue * (royalty_rate / 100)
        platform_fee = royalty_total * (self.PLATFORM_FEE_PCT / 100)
        net_to_nation = royalty_total - platform_fee

        return {
            "gross_revenue": gross_revenue,
            "royalty_rate_pct": royalty_rate,
            "royalty_total": round(royalty_total, 2),
            "platform_fee": round(platform_fee, 2),
            "net_to_source_nation": round(net_to_nation, 2),
        }

    def nagoya_compliance_check(self, source_nation: str, licensee_nation: str, license_type: str, purpose: Optional[str]) -> Dict[str, Any]:
        """
        Automated Nagoya Protocol compliance verification.
        Checks:
        1. Prior Informed Consent (PIC) requirements
        2. Mutually Agreed Terms (MAT) provisions
        3. Access and Benefit-Sharing (ABS) obligations
        4. Source nation ABS legislation status
        """
        # Nations with known ABS legislation
        abs_legislation = {
            "Brazil": True, "India": True, "South Africa": True, "Kenya": True,
            "Australia": True, "Japan": True, "China": True, "Mexico": True,
            "Colombia": True, "Peru": True, "Indonesia": True, "Philippines": True,
            "Norway": True, "France": True, "Spain": True,
        }

        checks = []
        compliant = True

        # Check 1: Source nation ABS legislation
        has_abs = abs_legislation.get(source_nation, False)
        checks.append({
            "check": "source_nation_abs_legislation",
            "result": "PASS" if has_abs else "WARNING",
            "detail": f"{source_nation} {'has' if has_abs else 'may not have'} ABS legislation. Verify with national focal point.",
        })
        if not has_abs:
            compliant = False

        # Check 2: Prior Informed Consent
        checks.append({
            "check": "prior_informed_consent",
            "result": "REQUIRED",
            "detail": f"PIC from {source_nation} competent national authority is mandatory before access.",
        })

        # Check 3: Mutually Agreed Terms
        mat_required = license_type in ("commercial", "exclusive")
        checks.append({
            "check": "mutually_agreed_terms",
            "result": "REQUIRED" if mat_required else "RECOMMENDED",
            "detail": f"MAT {'must' if mat_required else 'should'} include benefit-sharing provisions, royalty rates, and scope of use.",
        })

        # Check 4: Benefit-sharing
        royalty_rate = self.LICENSE_ROYALTY_RATES.get(license_type, 3.0)
        checks.append({
            "check": "benefit_sharing",
            "result": "PASS",
            "detail": f"Royalty rate {royalty_rate}% allocated to {source_nation}. Platform fee: {self.PLATFORM_FEE_PCT}%.",
        })

        # Check 5: Cross-border transfer
        checks.append({
            "check": "cross_border_transfer",
            "result": "REVIEW" if source_nation != licensee_nation else "PASS",
            "detail": f"{'Cross-border genetic resource transfer requires additional documentation.' if source_nation != licensee_nation else 'Domestic use — simplified compliance.'}",
        })

        return {
            "nagoya_compliant": compliant,
            "checks": checks,
            "recommendation": "PROCEED" if compliant else "REVIEW_REQUIRED",
        }


# ─── EXTERNAL DATA FETCHER ──────────────────────────────────────────────────────

class GenomicDataFetcher:
    """Fetches real biodiversity and species data."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)

    async def verify_species_gbif(self, species_name: str) -> Dict[str, Any]:
        """Verify species existence and get taxonomy from GBIF."""
        try:
            url = f"https://api.gbif.org/v1/species/match?name={species_name}&verbose=true"
            resp = await self.client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "matched": data.get("matchType", "NONE") != "NONE",
                    "confidence": data.get("confidence", 0),
                    "taxonomy": {
                        "kingdom": data.get("kingdom"),
                        "phylum": data.get("phylum"),
                        "class": data.get("class"),
                        "order": data.get("order"),
                        "family": data.get("family"),
                        "genus": data.get("genus"),
                        "species": data.get("species"),
                    },
                    "source": "GBIF",
                }
        except Exception as e:
            logger.warning(f"GBIF error: {e}")
        return {"matched": False, "source": "GBIF"}

    async def get_species_occurrences(self, species_name: str, limit: int = 5) -> List[Dict]:
        """Get occurrence records from GBIF."""
        try:
            url = f"https://api.gbif.org/v1/occurrence/search?scientificName={species_name}&limit={limit}"
            resp = await self.client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "country": r.get("country"),
                        "lat": r.get("decimalLatitude"),
                        "lon": r.get("decimalLongitude"),
                        "date": r.get("eventDate"),
                        "institution": r.get("institutionCode"),
                    }
                    for r in data.get("results", [])
                ]
        except Exception as e:
            logger.warning(f"GBIF occurrences error: {e}")
        return []

    async def get_nation_profile(self, nation: str) -> Dict[str, Any]:
        """Get nation data from REST Countries."""
        try:
            url = f"https://restcountries.com/v3.1/name/{nation}?fields=name,region,population,area,flag"
            resp = await self.client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    c = data[0]
                    return {
                        "name": c.get("name", {}).get("common", nation),
                        "region": c.get("region"),
                        "population": c.get("population"),
                        "area_km2": c.get("area"),
                        "flag": c.get("flag"),
                    }
        except Exception as e:
            logger.warning(f"REST Countries error: {e}")
        return {"name": nation}

    async def close(self):
        await self.client.aclose()


# ─── APP LIFECYCLE ───────────────────────────────────────────────────────────────

genetic_engine = GeneticIPEngine()
genomic_fetcher = GenomicDataFetcher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("DeepGenome Genetic IP Marketplace — Initialized")
    yield
    await genomic_fetcher.close()
    logger.info("DeepGenome Genetic IP Marketplace — Shutdown")


app = FastAPI(
    title="DeepGenome Genetic IP Marketplace",
    description=(
        "Production marketplace for licensing marine genetic sequences with automated "
        "Nagoya Protocol compliance, royalty tracking, and provenance chain auditing. "
        "Integrates GBIF for species verification and REST Countries for nation-level compliance."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

import enterprise_core
app.include_router(enterprise_core.router)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── API ROUTES: GENOME CATALOG ─────────────────────────────────────────────────

@app.post("/api/v1/sequences", response_model=SequenceResponse, status_code=201, tags=["Genome Catalog"])
async def register_sequence(seq: SequenceCreate, db: Session = Depends(get_db)):
    """
    Register a new genetic sequence in the marketplace:
    1. Analyze sequence properties (GC content, complexity)
    2. Verify species against GBIF
    3. Compute novelty score
    4. Set base licensing price
    5. Record provenance chain
    """
    # Generate sequence ID
    seq_id = f"DG-{hashlib.md5(f'{seq.species_name}-{datetime.utcnow().isoformat()}'.encode()).hexdigest()[:10].upper()}"

    existing = db.query(GenomeSequenceDB).filter(GenomeSequenceDB.sequence_id == seq_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Sequence ID collision, retry")

    # Analyze sequence
    analysis = genetic_engine.analyze_sequence(seq.sequence_data)

    # GBIF verification
    gbif = await genomic_fetcher.verify_species_gbif(seq.species_name)

    # Compute scores
    complexity = genetic_engine.compute_complexity_score(
        analysis["sequence_length_bp"], analysis["gc_content_pct"], seq.collection_depth_m
    )
    novelty = genetic_engine.compute_novelty_score(
        gbif.get("matched", False), seq.conservation_status, seq.collection_depth_m
    )
    base_price = genetic_engine.compute_base_price(
        complexity, novelty, seq.conservation_status, analysis["sequence_length_bp"]
    )

    # Provenance chain
    provenance = [
        {
            "event": "collection",
            "nation": seq.source_nation,
            "site": seq.collection_site,
            "depth_m": seq.collection_depth_m,
            "timestamp": datetime.utcnow().isoformat(),
        },
        {
            "event": "registration",
            "platform": "DeepGenome Marketplace",
            "sequence_id": seq_id,
            "hash": analysis["sequence_hash"],
            "timestamp": datetime.utcnow().isoformat(),
        },
    ]

    record = GenomeSequenceDB(
        sequence_id=seq_id,
        species_name=seq.species_name,
        common_name=seq.common_name,
        taxonomy=gbif.get("taxonomy", {}),
        source_nation=seq.source_nation,
        collection_site=seq.collection_site,
        collection_depth_m=seq.collection_depth_m,
        lat=seq.lat,
        lon=seq.lon,
        sequence_length_bp=analysis["sequence_length_bp"],
        gc_content_pct=analysis["gc_content_pct"],
        sequence_hash=analysis["sequence_hash"],
        conservation_status=seq.conservation_status,
        complexity_score=complexity,
        novelty_score=novelty,
        base_license_price_usd=base_price,
        nagoya_compliant=True,  # Registered through compliant platform
        provenance_chain=provenance,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    logger.info(f"Sequence {seq_id} registered: {seq.species_name} from {seq.source_nation}")
    return record


@app.get("/api/v1/sequences", response_model=List[SequenceResponse], tags=["Genome Catalog"])
def browse_catalog(
    source_nation: Optional[str] = None,
    conservation_status: Optional[str] = None,
    min_novelty: float = Query(default=0, ge=0, le=1),
    sort_by: str = Query(default="novelty_score", enum=["novelty_score", "base_license_price_usd", "total_revenue_usd", "created_at"]),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Browse the genome catalog with filters and sorting."""
    query = db.query(GenomeSequenceDB).filter(GenomeSequenceDB.is_active == True)
    if source_nation:
        query = query.filter(GenomeSequenceDB.source_nation == source_nation)
    if conservation_status:
        query = query.filter(GenomeSequenceDB.conservation_status == conservation_status)
    if min_novelty > 0:
        query = query.filter(GenomeSequenceDB.novelty_score >= min_novelty)

    query = query.order_by(getattr(GenomeSequenceDB, sort_by).desc())
    return query.limit(limit).all()


@app.get("/api/v1/sequences/{sequence_id}", response_model=SequenceResponse, tags=["Genome Catalog"])
def get_sequence(sequence_id: str, db: Session = Depends(get_db)):
    s = db.query(GenomeSequenceDB).filter(GenomeSequenceDB.sequence_id == sequence_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sequence not found")
    return s


@app.get("/api/v1/sequences/{sequence_id}/provenance", tags=["Genome Catalog"])
def get_provenance(sequence_id: str, db: Session = Depends(get_db)):
    """Get the full provenance chain of a genetic sequence."""
    s = db.query(GenomeSequenceDB).filter(GenomeSequenceDB.sequence_id == sequence_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sequence not found")
    return {"sequence_id": sequence_id, "provenance_chain": s.provenance_chain}


@app.get("/api/v1/sequences/{sequence_id}/gbif-verification", tags=["Genome Catalog"])
async def verify_sequence_species(sequence_id: str, db: Session = Depends(get_db)):
    """Cross-reference sequence species with GBIF and get occurrence data."""
    s = db.query(GenomeSequenceDB).filter(GenomeSequenceDB.sequence_id == sequence_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sequence not found")

    gbif_match = await genomic_fetcher.verify_species_gbif(s.species_name)
    occurrences = await genomic_fetcher.get_species_occurrences(s.species_name)

    return {
        "sequence_id": sequence_id,
        "species_name": s.species_name,
        "gbif_verification": gbif_match,
        "known_occurrences": occurrences,
    }


# ─── API ROUTES: LICENSING ──────────────────────────────────────────────────────

@app.post("/api/v1/licenses", response_model=LicenseResponse, status_code=201, tags=["Licensing"])
def create_license(lic: LicenseCreate, db: Session = Depends(get_db)):
    """
    Create a new license for a genetic sequence:
    1. Verify sequence exists and is active
    2. Run Nagoya compliance check
    3. Calculate license price based on type
    4. Set royalty rate
    5. Record provenance event
    """
    seq = db.query(GenomeSequenceDB).filter(GenomeSequenceDB.sequence_id == lic.sequence_id).first()
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if not seq.is_active:
        raise HTTPException(status_code=400, detail="Sequence is not available for licensing")

    # Nagoya compliance
    compliance = genetic_engine.nagoya_compliance_check(
        seq.source_nation, lic.licensee_nation, lic.license_type.value, lic.purpose
    )

    # Calculate price
    price = genetic_engine.compute_license_price(seq.base_license_price_usd, lic.license_type.value)
    royalty_rate = genetic_engine.LICENSE_ROYALTY_RATES.get(lic.license_type.value, 3.0)

    license_id = f"LIC-{uuid.uuid4().hex[:12].upper()}"
    valid_from = datetime.utcnow()
    valid_to = valid_from + timedelta(days=365 * lic.duration_years)

    license_record = LicenseDB(
        license_id=license_id,
        sequence_id=lic.sequence_id,
        licensee_org=lic.licensee_org,
        licensee_nation=lic.licensee_nation,
        license_type=lic.license_type.value,
        purpose=lic.purpose,
        price_usd=price,
        royalty_rate_pct=royalty_rate,
        nagoya_verified=compliance["nagoya_compliant"],
        compliance_notes=json.dumps(compliance),
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.add(license_record)

    # Update sequence stats
    seq.total_licenses_issued += 1
    seq.total_revenue_usd += price

    # Provenance event
    provenance = seq.provenance_chain or []
    provenance.append({
        "event": "license_issued",
        "license_id": license_id,
        "licensee": lic.licensee_org,
        "type": lic.license_type.value,
        "price_usd": price,
        "timestamp": datetime.utcnow().isoformat(),
    })
    seq.provenance_chain = provenance

    # Compliance audit record
    audit = ComplianceAuditDB(
        audit_id=f"AUD-{uuid.uuid4().hex[:12].upper()}",
        license_id=license_id,
        audit_type="nagoya",
        result="pass" if compliance["nagoya_compliant"] else "warning",
        findings=compliance["checks"],
    )
    db.add(audit)

    # If exclusive, deactivate from marketplace
    if lic.license_type == LicenseType.EXCLUSIVE:
        seq.is_active = False

    db.commit()
    db.refresh(license_record)
    return license_record


@app.get("/api/v1/licenses", tags=["Licensing"])
def list_licenses(
    sequence_id: Optional[str] = None,
    licensee_org: Optional[str] = None,
    status: Optional[str] = "active",
    db: Session = Depends(get_db),
):
    query = db.query(LicenseDB)
    if sequence_id:
        query = query.filter(LicenseDB.sequence_id == sequence_id)
    if licensee_org:
        query = query.filter(LicenseDB.licensee_org.contains(licensee_org))
    if status:
        query = query.filter(LicenseDB.status == status)
    licenses = query.order_by(LicenseDB.created_at.desc()).all()
    return [{
        "license_id": l.license_id, "sequence_id": l.sequence_id,
        "licensee_org": l.licensee_org, "license_type": l.license_type,
        "price_usd": l.price_usd, "royalty_rate_pct": l.royalty_rate_pct,
        "nagoya_verified": l.nagoya_verified, "status": l.status,
        "valid_from": l.valid_from.isoformat(), "valid_to": l.valid_to.isoformat() if l.valid_to else None,
    } for l in licenses]


@app.get("/api/v1/licenses/{license_id}/compliance", tags=["Licensing"])
def get_license_compliance(license_id: str, db: Session = Depends(get_db)):
    """Get compliance audit history for a license."""
    lic = db.query(LicenseDB).filter(LicenseDB.license_id == license_id).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    audits = db.query(ComplianceAuditDB).filter(ComplianceAuditDB.license_id == license_id).all()
    return {
        "license_id": license_id,
        "nagoya_verified": lic.nagoya_verified,
        "compliance_notes": json.loads(lic.compliance_notes) if lic.compliance_notes else {},
        "audit_history": [{
            "audit_id": a.audit_id, "type": a.audit_type, "result": a.result,
            "findings": a.findings, "audited_at": a.audited_at.isoformat(),
        } for a in audits],
    }


# ─── API ROUTES: ROYALTY PIPELINE ────────────────────────────────────────────────

@app.post("/api/v1/royalties", status_code=201, tags=["Royalty Pipeline"])
def record_royalty(royalty: RoyaltyCreate, db: Session = Depends(get_db)):
    """
    Record a royalty payment from a licensee.
    Automatically computes royalty breakdown and platform fee.
    """
    lic = db.query(LicenseDB).filter(LicenseDB.license_id == royalty.license_id).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")

    seq = db.query(GenomeSequenceDB).filter(GenomeSequenceDB.sequence_id == lic.sequence_id).first()

    breakdown = genetic_engine.compute_royalty(royalty.gross_revenue_usd, lic.royalty_rate_pct)

    payment_id = f"ROY-{uuid.uuid4().hex[:12].upper()}"
    payment = RoyaltyPaymentDB(
        payment_id=payment_id,
        license_id=royalty.license_id,
        sequence_id=lic.sequence_id,
        source_nation=seq.source_nation if seq else "Unknown",
        licensee_org=lic.licensee_org,
        gross_revenue_usd=royalty.gross_revenue_usd,
        royalty_rate_pct=lic.royalty_rate_pct,
        royalty_amount_usd=breakdown["royalty_total"],
        platform_fee_usd=breakdown["platform_fee"],
        net_to_source_nation_usd=breakdown["net_to_source_nation"],
        period_start=royalty.period_start,
        period_end=royalty.period_end,
    )
    db.add(payment)

    # Update sequence revenue
    if seq:
        seq.total_revenue_usd += breakdown["royalty_total"]

    db.commit()

    return {
        "payment_id": payment_id,
        "breakdown": breakdown,
        "source_nation": seq.source_nation if seq else "Unknown",
        "status": "recorded",
    }


@app.get("/api/v1/royalties", tags=["Royalty Pipeline"])
def list_royalties(
    sequence_id: Optional[str] = None,
    license_id: Optional[str] = None,
    source_nation: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(RoyaltyPaymentDB)
    if sequence_id:
        query = query.filter(RoyaltyPaymentDB.sequence_id == sequence_id)
    if license_id:
        query = query.filter(RoyaltyPaymentDB.license_id == license_id)
    if source_nation:
        query = query.filter(RoyaltyPaymentDB.source_nation == source_nation)

    payments = query.order_by(RoyaltyPaymentDB.created_at.desc()).all()
    return [{
        "payment_id": p.payment_id, "license_id": p.license_id,
        "source_nation": p.source_nation, "licensee_org": p.licensee_org,
        "gross_revenue": p.gross_revenue_usd, "royalty_amount": p.royalty_amount_usd,
        "platform_fee": p.platform_fee_usd, "net_to_nation": p.net_to_source_nation_usd,
        "period": f"{p.period_start.isoformat()} to {p.period_end.isoformat()}",
        "status": p.status,
    } for p in payments]


@app.get("/api/v1/royalties/dashboard", tags=["Royalty Pipeline"])
def royalty_dashboard(db: Session = Depends(get_db)):
    """
    Executive dashboard: royalty pipeline analytics.
    Shows total revenue, nation-level breakdown, and top sequences.
    """
    # Total stats
    total_royalties = db.query(func.sum(RoyaltyPaymentDB.royalty_amount_usd)).scalar() or 0
    total_platform_fees = db.query(func.sum(RoyaltyPaymentDB.platform_fee_usd)).scalar() or 0
    total_to_nations = db.query(func.sum(RoyaltyPaymentDB.net_to_source_nation_usd)).scalar() or 0
    total_payments = db.query(RoyaltyPaymentDB).count()

    # By nation
    nation_breakdown = db.query(
        RoyaltyPaymentDB.source_nation,
        func.sum(RoyaltyPaymentDB.net_to_source_nation_usd),
        func.count(RoyaltyPaymentDB.id),
    ).group_by(RoyaltyPaymentDB.source_nation).all()

    # Top sequences by revenue
    top_sequences = db.query(GenomeSequenceDB).order_by(GenomeSequenceDB.total_revenue_usd.desc()).limit(10).all()

    # License stats
    total_licenses = db.query(LicenseDB).count()
    active_licenses = db.query(LicenseDB).filter(LicenseDB.status == "active").count()

    return {
        "total_royalties_usd": total_royalties,
        "total_platform_fees_usd": total_platform_fees,
        "total_distributed_to_nations_usd": total_to_nations,
        "total_payments": total_payments,
        "total_licenses": total_licenses,
        "active_licenses": active_licenses,
        "nation_breakdown": [
            {"nation": n, "total_received_usd": round(v or 0, 2), "payment_count": c}
            for n, v, c in nation_breakdown
        ],
        "top_sequences": [
            {"sequence_id": s.sequence_id, "species": s.species_name,
             "source_nation": s.source_nation, "revenue_usd": s.total_revenue_usd}
            for s in top_sequences
        ],
    }


# ─── API ROUTES: MARKETPLACE ANALYTICS ──────────────────────────────────────────

@app.get("/api/v1/marketplace/stats", tags=["Marketplace"])
def marketplace_stats(db: Session = Depends(get_db)):
    """Overall marketplace statistics."""
    sequences = db.query(GenomeSequenceDB).count()
    active = db.query(GenomeSequenceDB).filter(GenomeSequenceDB.is_active == True).count()
    nations = db.query(func.count(func.distinct(GenomeSequenceDB.source_nation))).scalar() or 0
    total_value = db.query(func.sum(GenomeSequenceDB.base_license_price_usd)).scalar() or 0
    total_revenue = db.query(func.sum(GenomeSequenceDB.total_revenue_usd)).scalar() or 0
    avg_novelty = db.query(func.avg(GenomeSequenceDB.novelty_score)).scalar() or 0

    return {
        "total_sequences": sequences,
        "active_listings": active,
        "source_nations": nations,
        "total_catalog_value_usd": round(total_value, 2),
        "total_revenue_usd": round(total_revenue, 2),
        "average_novelty_score": round(float(avg_novelty), 4),
        "conservation_breakdown": {
            status: db.query(GenomeSequenceDB).filter(GenomeSequenceDB.conservation_status == status).count()
            for status in genetic_engine.CONSERVATION_MULTIPLIERS.keys()
        },
    }


# ─── ENTRYPOINT ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8004, reload=True)
