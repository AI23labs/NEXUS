"""
HTTP routes (RFC Section 2, Appendix A). Dashboard, state machine, manual overrides.
All under /api. 10s timeout on tool calls.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, time, timezone
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import Appointment, Campaign, CallTask, get_db_session, get_session_factory
from app.models import (
    BookSlotRequest,
    BookSlotResponse,
    CampaignRequest,
    CheckAvailabilityRequest,
    CheckAvailabilityResponse,
    ConfirmCampaignRequest,
    EndCallRequest,
    GetDistanceRequest,
    GetDistanceResponse,
    ReportSlotOfferRequest,
    ReportSlotOfferResponse,
    SwarmPlan,
)
from app.api.auth import get_current_user_id
from app.services.calendar_service import get_appointment_service
from app.services.orchestrator import SwarmOrchestrator
from app.services.orchestrator import create_campaign_and_swarm as orchestrator_create_campaign
from app.services.tools import dispatch_tool_call
from app.utils.date_parse import parse_date_flexible, parse_time_flexible
from openai import AsyncOpenAI

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api", tags=["api"])

TOOL_TIMEOUT_SECONDS = 10
SSE_POLL_INTERVAL = 2.0
SSE_PING_INTERVAL = 30


@router.post("/campaigns", response_model=SwarmPlan)
async def create_campaign(
    request: Request,
    body: CampaignRequest,
) -> SwarmPlan:
    """
    Create campaign in DB and spawn 15 concurrent call-agent tasks (RFC 3.2, Challenge 2.3).
    Requires authenticated user (session cookie). Match quality: Earliest 50%, Rating 30%, Proximity 20%.
    """
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    orchestrator = SwarmOrchestrator(openai_client=client)
    try:
        plan = await asyncio.wait_for(
            orchestrator_create_campaign(orchestrator, body, user_id=user_id),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("create_campaign_timeout", event_type="routes")
        raise HTTPException(status_code=504, detail="Campaign creation timed out") from None
    except Exception as e:
        logger.exception("create_campaign_error", error=str(e), event_type="routes")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return plan


@router.post("/check-availability", response_model=CheckAvailabilityResponse)
async def check_availability(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> CheckAvailabilityResponse:
    """
    RFC 6.1: Call AppointmentService.check_and_hold_slot. Accepts flexible date/time (e.g. 'Friday', '10 AM') for ElevenLabs.
    """
    try:
        raw = await request.json()
    except Exception:
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    # ElevenLabs may send date_str/time_str; our schema expects date/time
    if raw.get("date_str") is not None and not raw.get("date"):
        raw["date"] = raw["date_str"]
    if raw.get("time_str") is not None and not raw.get("time"):
        raw["time"] = raw["time_str"]
    # Normalize date/time for agent (e.g. "Friday" -> YYYY-MM-DD, "10 AM" -> 10:00)
    if raw.get("date"):
        parsed = parse_date_flexible(str(raw["date"]))
        if parsed:
            raw["date"] = parsed
    if raw.get("time"):
        parsed = parse_time_flexible(str(raw["time"]))
        if parsed:
            raw["time"] = parsed
    try:
        body = CheckAvailabilityRequest(**raw)
    except Exception as e:
        logger.warning("check_availability_validation", error=str(e), raw=raw, event_type="routes")
        raise HTTPException(status_code=422, detail=f"Invalid request. Use date YYYY-MM-DD and time HH:MM 24h. Error: {e}") from e
    campaign_id = body.campaign_id or "default_campaign"
    call_task_id = body.call_task_id or "default_call_task"
    user_id = body.user_id or "default_user"
    log = logger.bind(campaign_id=campaign_id, event_type="routes")
    svc = get_appointment_service()
    try:
        result = await asyncio.wait_for(
            svc.check_and_hold_slot(
                session,
                user_id=user_id,
                campaign_id=campaign_id,
                call_task_id=call_task_id,
                date_str=body.date,
                time_str=body.time,
                duration_minutes=body.duration_minutes,
                campaign_id_for_log=campaign_id,
            ),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.warning("check_availability_timeout", timeout_sec=TOOL_TIMEOUT_SECONDS)
        raise HTTPException(status_code=503, detail="Availability check timed out") from None
    except Exception as e:
        log.exception("check_availability_error", error=str(e))
        raise HTTPException(status_code=503, detail="Availability service unavailable") from e

    # RFC 3.6: Append successful hold key to CallTask.hold_keys for cleanup (non-negotiable)
    if result.get("status") == "held" and result.get("hold_key") and call_task_id != "default_call_task":
        try:
            r = await session.execute(select(CallTask).where(CallTask.id == UUID(call_task_id)))
            ct = r.scalar_one_or_none()
            if ct is not None:
                current = list(ct.hold_keys) if ct.hold_keys else []
                if result["hold_key"] not in current:
                    current.append(result["hold_key"])
                    await session.execute(
                        update(CallTask)
                        .where(CallTask.id == UUID(call_task_id))
                        .values(hold_keys=current, updated_at=datetime.now(timezone.utc))
                    )
                    await session.flush()
                    log.info("call_task_hold_key_appended", call_task_id=call_task_id, hold_key=result["hold_key"])
        except Exception as e:
            log.warning("hold_key_append_failed", call_task_id=call_task_id, error=str(e))

    return CheckAvailabilityResponse(
        status=result["status"],
        conflicts=result.get("conflicts", []),
        held_by=result.get("held_by"),
        next_free_slot=result.get("next_free_slot"),
        hold_expires_in_seconds=result.get("hold_expires_in_seconds"),
    )


@router.post("/book-slot", response_model=BookSlotResponse)
async def book_slot(
    body: BookSlotRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BookSlotResponse:
    """
    RFC 6.3 & 3.3: Call AppointmentService.confirm_and_book (lock, persist, release holds, kill).
    """
    log = logger.bind(campaign_id=body.campaign_id, event_type="routes")
    try:
        parsed_date = date.fromisoformat(body.appointment_date)
        hour, minute = int(body.appointment_time[:2]), int(body.appointment_time[3:5])
        parsed_time = time(hour, minute)
    except (ValueError, IndexError) as e:
        log.warning("book_slot_invalid_datetime", error=str(e))
        raise HTTPException(status_code=422, detail="Invalid date or time") from e

    svc = get_appointment_service()
    try:
        success, reason, _calendar_synced = await asyncio.wait_for(
            svc.confirm_and_book(
                session,
                campaign_id=body.campaign_id,
                call_task_id=body.call_task_id,
                user_id=body.user_id,
                provider_id=body.provider_id,
                provider_name=body.provider_name,
                provider_phone=body.provider_phone,
                provider_address=body.provider_address,
                appointment_date=parsed_date,
                appointment_time=parsed_time,
                duration_min=body.duration_min,
                doctor_name=body.doctor_name,
                hold_keys_to_release=body.hold_keys_to_release,
                campaign_id_for_log=body.campaign_id,
            ),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.warning("book_slot_timeout", timeout_sec=TOOL_TIMEOUT_SECONDS)
        raise HTTPException(status_code=504, detail="Booking timed out") from None
    except Exception as e:
        log.exception("book_slot_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
    return BookSlotResponse(booked=success, reason=reason)


@router.post("/end-call")
async def end_call(
    body: EndCallRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """
    Update call task status in DB and release Redis holds (RFC 3.3 Step 5).
    If call_task_id is missing or not a valid UUID, resolve from campaign's call tasks (use first active or latest).
    """
    from datetime import datetime, timezone
    from uuid import UUID

    from sqlalchemy import update

    from app.core.database import CallTask

    log = logger.bind(campaign_id=body.campaign_id, event_type="routes")
    call_task_id = (body.call_task_id or "").strip()
    if call_task_id:
        try:
            UUID(call_task_id)
        except (ValueError, TypeError):
            call_task_id = ""
    if not call_task_id:
        try:
            c_uid = UUID(body.campaign_id)
            r = await session.execute(
                select(CallTask).where(CallTask.campaign_id == c_uid).order_by(CallTask.updated_at.desc()).limit(1)
            )
            ct = r.scalar_one_or_none()
            if ct:
                call_task_id = str(ct.id)
                log.info("end_call_resolved_task", call_task_id=call_task_id)
        except (ValueError, TypeError):
            pass
    if not call_task_id:
        log.warning("end_call_missing_call_task_id", campaign_id=body.campaign_id)
        return {"status": "error", "message": "Missing call_task_id and could not resolve from campaign"}
    try:
        await session.execute(
            update(CallTask)
            .where(CallTask.id == UUID(call_task_id))
            .values(
                status=body.status,
                ended_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.flush()
    except Exception as e:
        log.exception("end_call_update_failed", error=str(e))
    svc = get_appointment_service()
    try:
        await asyncio.wait_for(
            svc.release_holds_for_campaign(body.hold_keys, campaign_id_for_log=body.campaign_id),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.warning("end_call_release_timeout")
    except Exception as e:
        log.exception("end_call_error", error=str(e))
    return {"status": "ok", "message": "Call ended and hold keys released"}


@router.post("/report-slot-offer", response_model=ReportSlotOfferResponse)
async def report_slot_offer_route(
    body: ReportSlotOfferRequest,
) -> ReportSlotOfferResponse:
    """
    RFC 6.2: ElevenLabs agent reports a calendar-held slot. Persists to CallTask, transitions campaign to RANKING.
    """
    log = logger.bind(campaign_id=body.campaign_id, call_task_id=body.call_task_id, event_type="routes")
    from app.services.tools import report_slot_offer
    try:
        result_json = await asyncio.wait_for(
            report_slot_offer(
                provider_name=body.provider_name,
                date_str=body.date,
                time_str=body.time,
                duration_minutes=body.duration_minutes,
                doctor_name=body.doctor_name,
                campaign_id=body.campaign_id,
                call_task_id=body.call_task_id,
            ),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        out = json.loads(result_json)
        # instruction must be "continue_holding" or "terminate" per schema
        inst = out.get("instruction") or "continue_holding"
        if inst not in ("continue_holding", "terminate"):
            inst = "continue_holding"
        return ReportSlotOfferResponse(
            received=out.get("received", False),
            ranking_position=out.get("ranking_position", 1),
            instruction=inst,
        )
    except asyncio.TimeoutError:
        log.warning("report_slot_offer_timeout")
        return ReportSlotOfferResponse(received=False, ranking_position=0, instruction="continue_holding")
    except Exception as e:
        log.exception("report_slot_offer_error", error=str(e))
        return ReportSlotOfferResponse(received=False, ranking_position=0, instruction="continue_holding")


@router.post("/get-distance", response_model=GetDistanceResponse)
async def get_distance_route(body: GetDistanceRequest) -> GetDistanceResponse:
    """
    RFC 6.4: ElevenLabs tool — distance and travel time to destination. Uses Google Distance Matrix when GOOGLE_API_KEY set.
    """
    from app.services.tools import get_distance
    try:
        result_json = await asyncio.wait_for(
            get_distance(destination_address=body.destination_address),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        out = json.loads(result_json)
        return GetDistanceResponse(
            distance_km=float(out.get("distance_km", 5.0)),
            travel_time_min=int(out.get("travel_time_min", 12)),
            mode=out.get("mode", "driving"),
        )
    except (asyncio.TimeoutError, ValueError) as e:
        logger.warning("get_distance_failed", error=str(e), event_type="routes")
        return GetDistanceResponse(distance_km=5.0, travel_time_min=12, mode="driving")


class AgenticToolRequest(BaseModel):
    """Unified webhook: ElevenLabs sends tool_name + arguments."""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.post("/tools")
async def agentic_tool_webhook(body: AgenticToolRequest) -> Any:
    """
    Single webhook URL for ElevenLabs Agentic Functions. POST with {"tool_name": "...", "arguments": {...}}.
    Dispatches to check_availability, book_slot, report_slot_offer, or get_distance. Returns JSON string result.
    """
    log = logger.bind(tool_name=body.tool_name, event_type="routes")
    try:
        result = await asyncio.wait_for(
            dispatch_tool_call(body.tool_name, body.arguments),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        return json.loads(result) if result.strip().startswith("{") else {"result": result}
    except asyncio.TimeoutError:
        log.warning("agentic_tool_timeout")
        raise HTTPException(status_code=504, detail="Tool timeout") from None
    except Exception as e:
        log.exception("agentic_tool_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


# ----- Read endpoints & dashboard (RFC Appendix A) -----


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str) -> dict:
    """Get campaign status and metadata."""
    try:
        uid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid campaign ID")
    factory = get_session_factory()
    async with factory() as session:
        r = await session.execute(select(Campaign).where(Campaign.id == uid))
        campaign = r.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {
        "id": str(campaign.id),
        "user_id": str(campaign.user_id),
        "status": campaign.status,
        "service_type": campaign.service_type,
        "query_text": campaign.query_text,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
        "confirmed_call_task_id": str(campaign.confirmed_call_task_id) if campaign.confirmed_call_task_id else None,
    }


def _serialize_call_task(ct: CallTask) -> dict:
    return {
        "id": str(ct.id),
        "campaign_id": str(ct.campaign_id),
        "provider_id": ct.provider_id,
        "provider_name": ct.provider_name,
        "provider_phone": ct.provider_phone,
        "status": ct.status,
        "score": ct.score,
        "offered_date": ct.offered_date.isoformat() if ct.offered_date else None,
        "offered_time": ct.offered_time.strftime("%H:%M") if ct.offered_time else None,
        "offered_duration_min": ct.offered_duration_min,
        "offered_doctor": ct.offered_doctor,
        "hold_keys": ct.hold_keys or [],
        "started_at": ct.started_at.isoformat() if ct.started_at else None,
        "ended_at": ct.ended_at.isoformat() if ct.ended_at else None,
        "updated_at": ct.updated_at.isoformat() if ct.updated_at else None,
    }


@router.get("/campaigns/{campaign_id}/stream")
async def campaign_stream(campaign_id: str):
    """
    RFC Appendix A: SSE stream for real-time swarm status. Yields JSON on CallTask status change.
    30-second :ping heartbeat for reverse proxies.
    """
    try:
        uid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid campaign ID")

    async def event_stream():
        last_snapshot: str | None = None
        last_ping = asyncio.get_running_loop().time()
        log = logger.bind(campaign_id=campaign_id, event_type="stream")
        factory = get_session_factory()
        while True:
            try:
                now = asyncio.get_running_loop().time()
                if now - last_ping >= SSE_PING_INTERVAL:
                    yield ": ping\n\n"
                    last_ping = now

                async with factory() as session:
                    r = await session.execute(
                        select(Campaign).where(Campaign.id == uid)
                    )
                    campaign = r.scalar_one_or_none()
                    if not campaign:
                        yield f"data: {json.dumps({'error': 'Campaign not found'})}\n\n"
                        return
                    r2 = await session.execute(
                        select(CallTask).where(CallTask.campaign_id == uid).order_by(CallTask.updated_at.desc())
                    )
                    tasks = list(r2.scalars().all())
                payload = {
                    "campaign_id": campaign_id,
                    "campaign_status": campaign.status,
                    "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
                    "call_tasks": [_serialize_call_task(t) for t in tasks],
                }
                snapshot = json.dumps(payload, default=str)
                if snapshot != last_snapshot:
                    yield f"data: {snapshot}\n\n"
                    last_snapshot = snapshot
                    log.info("stream_event", timestamp_ms=round(datetime.now(timezone.utc).timestamp() * 1000))

                if campaign.status in ("confirmed", "failed", "cancelled"):
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception("stream_error", error=str(e))
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
            await asyncio.sleep(SSE_POLL_INTERVAL)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/campaigns/{campaign_id}/results")
async def campaign_results(campaign_id: str) -> dict:
    """Return ranked list of slot offers (CallTasks with offers), sorted by match quality score."""
    try:
        uid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid campaign ID")
    factory = get_session_factory()
    async with factory() as session:
        r = await session.execute(
            select(CallTask)
            .where(CallTask.campaign_id == uid)
            .where(CallTask.status == "slot_offered")
            .order_by(CallTask.score.desc().nulls_last())
        )
        tasks = list(r.scalars().all())
    return {
        "campaign_id": campaign_id,
        "offers": [_serialize_call_task(t) for t in tasks],
    }


@router.post("/campaigns/{campaign_id}/confirm")
async def confirm_campaign(campaign_id: str, body: ConfirmCampaignRequest, session: AsyncSession = Depends(get_db_session)) -> dict:
    """
    Manual override (Challenge 3.0): Force confirm selected slot. Triggers confirm_and_book and kill signal.
    """
    log = logger.bind(campaign_id=campaign_id, event_type="routes")
    try:
        c_uid = UUID(campaign_id)
        ct_uid = UUID(body.call_task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid campaign or call_task ID")

    async with get_session_factory()() as sess:
        r = await sess.execute(select(Campaign).where(Campaign.id == c_uid))
        campaign = r.scalar_one_or_none()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        r2 = await sess.execute(select(CallTask).where(CallTask.id == ct_uid).where(CallTask.campaign_id == c_uid))
        winning = r2.scalar_one_or_none()
        if not winning:
            raise HTTPException(status_code=404, detail="Call task not found or not in this campaign")
        if not winning.offered_date or not winning.offered_time:
            raise HTTPException(status_code=422, detail="Selected call task has no slot offer")
        r3 = await sess.execute(select(CallTask).where(CallTask.campaign_id == c_uid))
        all_tasks = list(r3.scalars().all())
    hold_keys_to_release = []
    for t in all_tasks:
        if t.id != ct_uid and getattr(t, "hold_keys", None) and isinstance(t.hold_keys, list):
            hold_keys_to_release.extend(t.hold_keys)

    user_id = str(campaign.user_id)
    appointment_date = winning.offered_date
    appointment_time = winning.offered_time
    duration_min = winning.offered_duration_min or 30
    svc = get_appointment_service()
    success, reason, calendar_synced = await asyncio.wait_for(
        svc.confirm_and_book(
            session,
            campaign_id=campaign_id,
            call_task_id=body.call_task_id,
            user_id=user_id,
            provider_id=winning.provider_id,
            provider_name=winning.provider_name,
            provider_phone=winning.provider_phone,
            provider_address=None,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            duration_min=duration_min,
            doctor_name=winning.offered_doctor,
            hold_keys_to_release=hold_keys_to_release,
            campaign_id_for_log=campaign_id,
        ),
        timeout=TOOL_TIMEOUT_SECONDS,
    )
    if not success:
        log.warning("confirm_failed", reason=reason)
        raise HTTPException(status_code=409, detail=reason or "Booking failed")
    log.info("campaign_confirmed", call_task_id=body.call_task_id, calendar_synced=calendar_synced, timestamp_ms=round(datetime.now(timezone.utc).timestamp() * 1000))
    return {"status": "confirmed", "call_task_id": body.call_task_id, "calendar_synced": calendar_synced, "message": "Slot confirmed and kill signal sent"}


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: str) -> dict:
    """Manual override: Cancel campaign, publish kill, release all Redis holds."""
    log = logger.bind(campaign_id=campaign_id, event_type="routes")
    try:
        c_uid = UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid campaign ID")

    factory = get_session_factory()
    async with factory() as session:
        r = await session.execute(select(Campaign).where(Campaign.id == c_uid))
        campaign = r.scalar_one_or_none()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        await session.execute(
            update(Campaign).where(Campaign.id == c_uid).values(status="cancelled", updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
        r2 = await session.execute(select(CallTask).where(CallTask.campaign_id == c_uid))
        tasks = list(r2.scalars().all())
    hold_keys = []
    for t in tasks:
        if getattr(t, "hold_keys", None) and isinstance(t.hold_keys, list):
            hold_keys.extend(t.hold_keys)
    if hold_keys:
        svc = get_appointment_service()
        await svc.release_holds_for_campaign(hold_keys, campaign_id_for_log=campaign_id)
    redis_client = await get_appointment_service()._redis_client()
    await redis_client.publish(f"kill:{campaign_id}", "cancel")
    log.info("campaign_cancelled", timestamp_ms=round(datetime.now(timezone.utc).timestamp() * 1000))
    return {"status": "cancelled", "message": "Campaign cancelled, kill signal sent, holds released"}


@router.get("/appointments")
async def list_appointments() -> dict:
    """Return all confirmed appointments from PostgreSQL (RFC Appendix A)."""
    factory = get_session_factory()
    async with factory() as session:
        r = await session.execute(
            select(Appointment).where(Appointment.status == "confirmed").order_by(Appointment.created_at.desc())
        )
        rows = list(r.scalars().all())
    return {
        "appointments": [
            {
                "id": str(a.id),
                "campaign_id": str(a.campaign_id),
                "call_task_id": str(a.call_task_id),
                "user_id": a.user_id,
                "provider_id": a.provider_id,
                "provider_name": a.provider_name,
                "provider_phone": a.provider_phone,
                "appointment_date": a.appointment_date.isoformat(),
                "appointment_time": a.appointment_time.strftime("%H:%M"),
                "duration_min": a.duration_min,
                "doctor_name": a.doctor_name,
                "calendar_synced": a.calendar_synced,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in rows
        ],
    }
