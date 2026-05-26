import os
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from http import HTTPStatus
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


SERVICE_NAME = os.getenv("SERVICE_NAME", "access-gate")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "local-dev-token")

POLICY_ID = UUID("0196fb3d-4ad7-7d1e-9f49-5d5148d2bac0")
TIME_RULE_ID = UUID("0196fb3d-4ad7-7d1e-9f49-5d5148d2bac2")
ROLE_RULE_ID = UUID("0196fb3d-4ad7-7d1e-9f49-5d5148d2bac3")


app = FastAPI(
    title="Smart Campus Access Gate Policy Service",
    version=SERVICE_VERSION,
    description="Dockerized Access Gate service aligned with the Pair 10 Gate/Core OpenAPI contract.",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Problem(StrictModel):
    type: str = "about:blank"
    title: str
    status: int = Field(..., ge=400, le=599)
    detail: Optional[str] = None
    instance: Optional[str] = None
    errors: List[Dict[str, str]] = Field(default_factory=list)


class HealthStatus(StrictModel):
    status: str
    service: str
    time: str


class Direction(str, Enum):
    IN = "IN"
    OUT = "OUT"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class PolicyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class AccessCheckRequest(StrictModel):
    cardId: str = Field(..., pattern=r"^RFID-[0-9]{4}-[0-9]{3}$")
    gateId: str = Field(..., pattern=r"^GATE-[0-9]{2}$")
    direction: Direction
    timestamp: datetime
    idempotencyKey: Optional[UUID] = None


class AccessCheckResponse(StrictModel):
    decisionId: UUID
    decision: Decision
    reasonCode: Optional[str] = None
    policyId: UUID
    expiresAt: Optional[str] = None
    checkedAt: str


class TimeBasedRule(StrictModel):
    ruleType: str = "TIME_BASED"
    ruleId: UUID
    startTime: str
    endTime: str
    allowedDays: List[str]


class RoleBasedRule(StrictModel):
    ruleType: str = "ROLE_BASED"
    ruleId: UUID
    allowedRoles: List[str]
    restrictedZones: Optional[List[str]] = None


class AccessPolicy(StrictModel):
    policyId: UUID
    name: str
    description: Optional[str] = None
    status: PolicyStatus
    rules: List[TimeBasedRule | RoleBasedRule]
    createdAt: str
    updatedAt: str


class AccessDecision(StrictModel):
    decisionId: UUID
    cardId: str
    gateId: str
    direction: Direction
    decision: Decision
    reasonCode: Optional[str] = None
    policyId: UUID
    expiresAt: Optional[str] = None
    checkedAt: str


class PolicyPage(StrictModel):
    items: List[AccessPolicy]
    nextCursor: Optional[str]
    hasMore: bool


class DecisionPage(StrictModel):
    items: List[AccessDecision]
    nextCursor: Optional[str]
    hasMore: bool


DECISIONS: Dict[str, AccessDecision] = {}
IDEMPOTENCY_KEYS: Dict[str, str] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def reason_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP Error"


def build_problem(
    *,
    status_code: int,
    title: str,
    detail: str,
    instance: Optional[str] = None,
    problem_type: str = "about:blank",
    errors: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    return {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "errors": errors or [],
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        problem = exc.detail
    else:
        problem = build_problem(
            status_code=exc.status_code,
            title=reason_phrase(exc.status_code),
            detail=str(exc.detail),
            instance=str(request.url.path),
        )

    problem.setdefault("type", "about:blank")
    problem.setdefault("title", reason_phrase(exc.status_code))
    problem.setdefault("status", exc.status_code)
    problem.setdefault("detail", "Request failed")
    problem.setdefault("instance", str(request.url.path))
    problem.setdefault("errors", [])

    return JSONResponse(
        status_code=exc.status_code,
        content=problem,
        media_type="application/problem+json",
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(item) for item in first_error.get("loc", []))
    message = first_error.get("msg", "Request validation error")
    field = location.split(".")[-1] if location else "request"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=build_problem(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Unprocessable Entity",
            detail=f"{location}: {message}" if location else message,
            instance=str(request.url.path),
            problem_type="https://campus.local/errors/validation",
            errors=[{"field": field, "code": "VALIDATION_ERROR", "message": message}],
        ),
        media_type="application/problem+json",
    )


def verify_bearer_token(authorization: Optional[str] = Header(default=None)) -> None:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_problem(
                status_code=status.HTTP_401_UNAUTHORIZED,
                title="Unauthorized",
                detail="Missing Bearer token",
                problem_type="https://campus.local/errors/unauthorized",
            ),
        )

    if authorization != f"Bearer {AUTH_TOKEN}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_problem(
                status_code=status.HTTP_401_UNAUTHORIZED,
                title="Unauthorized",
                detail="Invalid Bearer token",
                problem_type="https://campus.local/errors/unauthorized",
            ),
        )


def sample_policy() -> AccessPolicy:
    return AccessPolicy(
        policyId=POLICY_ID,
        name="Business hours - Zone A",
        description="Default access policy for Zone A during campus business hours",
        status=PolicyStatus.ACTIVE,
        rules=[
            TimeBasedRule(
                ruleId=TIME_RULE_ID,
                startTime="07:00",
                endTime="22:00",
                allowedDays=["MON", "TUE", "WED", "THU", "FRI"],
            ),
            RoleBasedRule(
                ruleId=ROLE_RULE_ID,
                allowedRoles=["STUDENT", "LECTURER", "STAFF"],
                restrictedZones=None,
            ),
        ],
        createdAt="2026-01-01T00:00:00+00:00",
        updatedAt="2026-05-01T00:00:00+00:00",
    )


def decision_id_from_count() -> UUID:
    suffix = len(DECISIONS) + 1
    return UUID(f"0196fb3d-4ad7-7d1e-9f49-5d5148d2{suffix:04x}")


def is_denied_card(card_id: str) -> bool:
    return card_id.endswith("999") or card_id.endswith("042")


@app.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    return HealthStatus(status="ok", service=SERVICE_NAME, time=now_iso())


@app.post(
    "/access/check",
    response_model=AccessCheckResponse,
    dependencies=[Depends(verify_bearer_token)],
)
def check_access_policy(payload: AccessCheckRequest) -> AccessCheckResponse:
    if payload.idempotencyKey:
        key = str(payload.idempotencyKey)
        if key in IDEMPOTENCY_KEYS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=build_problem(
                    status_code=status.HTTP_409_CONFLICT,
                    title="Conflict",
                    detail="Duplicate idempotency key",
                    problem_type="https://campus.local/errors/conflict",
                ),
            )

    checked_at = now_iso()
    allow = not is_denied_card(payload.cardId)
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="seconds")
        if allow
        else None
    )
    access_decision = AccessDecision(
        decisionId=decision_id_from_count(),
        cardId=payload.cardId,
        gateId=payload.gateId,
        direction=payload.direction,
        decision=Decision.ALLOW if allow else Decision.DENY,
        reasonCode=None if allow else "CARD_EXPIRED",
        policyId=POLICY_ID,
        expiresAt=expires_at,
        checkedAt=checked_at,
    )
    DECISIONS[str(access_decision.decisionId)] = access_decision

    if payload.idempotencyKey:
        IDEMPOTENCY_KEYS[str(payload.idempotencyKey)] = str(access_decision.decisionId)

    return AccessCheckResponse(
        decisionId=access_decision.decisionId,
        decision=access_decision.decision,
        reasonCode=access_decision.reasonCode,
        policyId=access_decision.policyId,
        expiresAt=access_decision.expiresAt,
        checkedAt=access_decision.checkedAt,
    )


@app.get(
    "/policies/access",
    response_model=PolicyPage,
    dependencies=[Depends(verify_bearer_token)],
)
def list_access_policies(
    cursor: Optional[str] = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[PolicyStatus] = Query(default=None, alias="status"),
) -> PolicyPage:
    policy = sample_policy()
    items = [policy] if status_filter in (None, policy.status) else []
    return PolicyPage(items=items[:limit], nextCursor=None if not cursor else None, hasMore=False)


@app.get(
    "/policies/access/{policyId}",
    response_model=AccessPolicy,
    dependencies=[Depends(verify_bearer_token)],
)
def get_access_policy_by_id(policyId: UUID) -> AccessPolicy:
    if policyId == POLICY_ID:
        return sample_policy()

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=build_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail=f"Policy {policyId} does not exist",
            instance=f"/policies/access/{policyId}",
            problem_type="https://campus.local/errors/not-found",
        ),
    )


@app.get(
    "/decisions",
    response_model=DecisionPage,
    dependencies=[Depends(verify_bearer_token)],
)
def list_decisions(
    cursor: Optional[str] = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> DecisionPage:
    items = list(DECISIONS.values())
    return DecisionPage(items=items[:limit], nextCursor=None if not cursor else None, hasMore=False)


@app.get(
    "/decisions/{decisionId}",
    response_model=AccessDecision,
    dependencies=[Depends(verify_bearer_token)],
)
def get_decision_by_id(decisionId: UUID) -> AccessDecision:
    decision = DECISIONS.get(str(decisionId))
    if decision:
        return decision

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=build_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail=f"Decision {decisionId} does not exist",
            instance=f"/decisions/{decisionId}",
            problem_type="https://campus.local/errors/not-found",
        ),
    )


@app.post("/webhooks/policy-updated")
def on_policy_updated(payload: AccessPolicy) -> Dict[str, str]:
    return {"status": "received", "policyId": str(payload.policyId)}


@app.middleware("http")
async def reject_malformed_card_ids(request: Request, call_next):
    if request.url.path == "/access/check" and request.method == "POST":
        body = await request.body()
        if body and b"cardId" in body and not re.search(rb'"cardId"\s*:\s*"RFID-\d{4}-\d{3}"', body):
            # Let Pydantic produce the canonical 422 for invalid schema fields.
            pass
    return await call_next(request)
