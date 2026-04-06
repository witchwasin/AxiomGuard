"""
Axiom Studio API — FastAPI backend for the visual rule editor.

Endpoints:
  POST /api/verify     — Verify a claim against rules
  POST /api/validate   — Validate YAML string
  POST /api/build-yaml — Build YAML from rule list
  POST /api/generate   — Generate rules from text (AI-assisted)

Run:
  pip install "axiomguard[studio-v2]"
  python -m axiomguard.studio.app
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from axiomguard import KnowledgeBase, Claim
from axiomguard.studio.core import (
    build_yaml_output,
    validate_yaml_input,
    verify_claim_against_rules,
)

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, FileResponse
    from pydantic import BaseModel

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


# =====================================================================
# Request/Response Models
# =====================================================================

if _HAS_FASTAPI:

    class VerifyRequest(BaseModel):
        yaml_rules: str
        subject: str
        relation: str
        value: str

    class VerifyResponse(BaseModel):
        is_hallucinating: bool
        reason: str
        violated_rules: List[Dict[str, Any]]
        error: bool = False

    class ValidateRequest(BaseModel):
        yaml_str: str

    class ValidateResponse(BaseModel):
        valid: bool
        domain: str = ""
        rules: List[Dict[str, Any]] = []
        error: Optional[str] = None

    class BuildYamlRequest(BaseModel):
        domain: str
        rules: List[Dict[str, Any]]

    class BuildYamlResponse(BaseModel):
        yaml: str

    class GenerateRequest(BaseModel):
        text: str
        domain: str = "generated"

    class GenerateResponse(BaseModel):
        suggestions: List[Dict[str, Any]]
        error: Optional[str] = None


# =====================================================================
# FastAPI App
# =====================================================================


def create_app() -> "FastAPI":
    """Create the FastAPI application."""
    if not _HAS_FASTAPI:
        raise ImportError(
            "Axiom Studio v2 requires FastAPI. "
            "Install with: pip install 'axiomguard[studio-v2]'"
        )

    app = FastAPI(
        title="Axiom Studio API",
        description="Backend for AxiomGuard visual rule editor",
        version="0.7.2",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Verify endpoint ---
    @app.post("/api/verify", response_model=VerifyResponse)
    async def verify_claim(req: VerifyRequest):
        result = verify_claim_against_rules(
            yaml_str=req.yaml_rules,
            subject=req.subject,
            relation=req.relation,
            value=req.value,
        )
        return VerifyResponse(
            is_hallucinating=result["is_hallucinating"],
            reason=result["reason"],
            violated_rules=result.get("violated_rules", []),
            error=result.get("error", False),
        )

    # --- Validate endpoint ---
    @app.post("/api/validate", response_model=ValidateResponse)
    async def validate_yaml(req: ValidateRequest):
        result = validate_yaml_input(req.yaml_str)
        return ValidateResponse(
            valid=result["valid"],
            domain=result.get("domain", ""),
            rules=result.get("rules", []),
            error=result.get("error"),
        )

    # --- Build YAML endpoint ---
    @app.post("/api/build-yaml", response_model=BuildYamlResponse)
    async def build_yaml(req: BuildYamlRequest):
        yaml_str = build_yaml_output(domain=req.domain, rules=req.rules)
        return BuildYamlResponse(yaml=yaml_str)

    # --- Generate rules endpoint ---
    @app.post("/api/generate", response_model=GenerateResponse)
    async def generate_rules(req: GenerateRequest):
        """AI-assisted rule generation from policy text.

        Uses Tournament engine to generate candidate rules.
        Returns suggestions for human Approve/Edit/Reject.
        """
        try:
            from axiomguard.rule_generator import generate_rules as gen_rules

            yaml_str = gen_rules(
                text=req.text,
                domain=req.domain,
            )
            result = validate_yaml_input(yaml_str)
            if result["valid"]:
                return GenerateResponse(suggestions=result["rules"])
            else:
                return GenerateResponse(
                    suggestions=[],
                    error=f"Generation produced invalid YAML: {result['error']}",
                )
        except Exception as e:
            return GenerateResponse(
                suggestions=[],
                error=f"Rule generation requires an LLM backend. {e}",
            )

    # --- Health check ---
    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.7.2",
            "engine": "Z3 Theorem Prover",
        }

    return app
