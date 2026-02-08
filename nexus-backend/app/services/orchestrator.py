"""
Swarm orchestrator — RFC 3.2: Phase 1 + create campaign in DB, spawn 15 call-agent tasks.
State machine RFC 3.1: CREATED -> PROVIDER_LOOKUP -> DIALING -> NEGOTIATING -> RANKING -> CONFIRMED.
Match quality: Earliest Time 50%, Rating 30%, Proximity 20% (Challenge 2.3).
MOCK_HUMAN: route all calls to TARGET_PHONE_NUMBER; cap tasks at MOCK_HUMAN_MAX_CALLS.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import httpx
import structlog
from openai import AsyncOpenAI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import Campaign, CallTask, get_session_factory
from app.models.schemas import (
    AvailableSlot,
    CampaignIntent,
    CampaignRequest,
    Provider,
    ProviderLocation,
    SwarmPlan,
)
from app.services.calendar_service import get_appointment_service
from app.services.provider_service import get_provider_service

logger = structlog.get_logger(__name__)

MAX_CALL_AGENTS_LIVE = 15
CAMPAIGN_STALE_MINUTES = 5
CAMPAIGN_MONITOR_INTERVAL_SECONDS = 60
ELEVENLABS_OUTBOUND_TIMEOUT = 30.0
WEIGHT_EARLIEST = 0.5
WEIGHT_RATING = 0.3
WEIGHT_PROXIMITY = 0.2

# GPT-4o-mini brain instructions passed to ElevenLabs dynamic_variables (Challenge 2.2)
ELEVENLABS_BRAIN_INSTRUCTIONS = (
    "You are calling ON BEHALF OF THE CUSTOMER (e.g. Alex Carter). You are the caller; the other party is the receptionist. Never act as or speak for the receptionist. "
    "All times are in Pacific (PST/PDT, America/Los_Angeles). When you say times, use Pacific. "
    "You MUST use tools in this order; do not skip steps. "
    "1) check_availability: Call when the receptionist offers a date and time. Use target_date and target_time from context for date/time. "
    "2) report_slot_offer: Call immediately after check_availability returns 'held'. Use the same date and time you held, and the provider name the receptionist gave. Do not say the slot is confirmed until report_slot_offer is done. "
    "3) book_slot: When the receptionist agrees (e.g. 'Okay', 'That works', 'Sure', 'Yes'), you MUST call book_slot to finalize. Pass appointment_date, appointment_time, patient_name, patient_phone, provider_id, provider_name, provider_phone, duration_min (e.g. 30), campaign_id, call_task_id, user_id. Only AFTER book_slot returns success may you say the appointment is booked, confirmed, or in the system. Never say 'successfully booked', 'confirmed', or 'booked in the system' without having called book_slot first and received a successful response. If you have not yet called book_slot, say you will finalize the booking now and then call the tool. "
    "4) end_call: Call end_call ONLY after book_slot has been called and confirmed successful. When you have finished the booking and are saying goodbye, then call end_call with campaign_id, call_task_id, status 'completed', and hold_keys []. Do not call end_call before book_slot has succeeded. "
    "Use target_date and target_time from context for date/time. Never use past years (e.g. 2024). Do not invent provider details."
)


def _providers_15_fallback(service_type: str, location: str) -> list[Provider]:
    """Return 15 providers (RFC 3.5 cap). Single source for demo; replace with Places API in live."""
    base = {
        "type": service_type or "dentist",
        "address": location or "123 Main St",
        "language": "en",
        "timezone": "America/Los_Angeles",
        "receptionist_persona": "Friendly and efficient.",
        "business_hours": {"mon_fri": "9-17", "sat": "9-13", "sun": "closed"},
    }
    slots = [
        AvailableSlot(date="2026-02-10", time="09:00", duration_min=30, doctor="Dr. Smith"),
        AvailableSlot(date="2026-02-10", time="14:00", duration_min=30, doctor="Dr. Smith"),
        AvailableSlot(date="2026-02-11", time="10:00", duration_min=30, doctor="Dr. Jones"),
    ]
    templates = [
        ("mock-001", "Downtown Dental Care", "+15551234001", 4.8, 0.1, 37.7749, -122.4194, 120),
        ("mock-002", "Smile Plus Clinic", "+15551234002", 4.5, 0.2, 37.7849, -122.4094, 85),
        ("mock-003", "Quick Fix Dental", "+15551234003", 3.4, 0.5, 37.7649, -122.4294, 30),
        ("mock-004", "Elite Dental Studio", "+15551234004", 4.9, 0.0, 37.7699, -122.4144, 200),
        ("mock-005", "Budget Dental Co", "+15551234005", 2.8, 0.6, 37.7599, -122.4244, 15),
        ("mock-006", "Central Care", "+15551234006", 4.2, 0.2, 37.7700, -122.4200, 90),
        ("mock-007", "Westside Dental", "+15551234007", 4.6, 0.1, 37.7750, -122.4300, 110),
        ("mock-008", "East End Dental", "+15551234008", 3.8, 0.3, 37.7600, -122.4100, 45),
        ("mock-009", "North Park Dental", "+15551234009", 4.0, 0.4, 37.7800, -122.4150, 60),
        ("mock-010", "South Bay Dental", "+15551234010", 4.7, 0.1, 37.7550, -122.4250, 95),
        ("mock-011", "Metro Dental", "+15551234011", 3.6, 0.5, 37.7720, -122.4180, 40),
        ("mock-012", "Valley View Dental", "+15551234012", 4.3, 0.2, 37.7680, -122.4320, 75),
        ("mock-013", "Hillside Dental", "+15551234013", 3.9, 0.3, 37.7820, -122.4080, 55),
        ("mock-014", "Riverside Dental", "+15551234014", 4.4, 0.2, 37.7610, -122.4220, 80),
        ("mock-015", "Summit Dental", "+15551234015", 4.1, 0.3, 37.7780, -122.4120, 65),
    ]
    return [
        Provider(
            id=t[0],
            name=t[1],
            phone=t[2],
            rating=t[3],
            rejection_probability=t[4],
            location=ProviderLocation(lat=t[5], lng=t[6]),
            rating_count=t[7],
            available_slots=slots,
            **base,
        )
        for t in templates
    ]


async def _transition_campaign_status(
    campaign_id: str, new_status: str, only_if_current: list[str] | None = None
) -> None:
    """RFC 3.1: Drive campaign state machine. If only_if_current is set, update only when status in list."""
    log = logger.bind(campaign_id=campaign_id, event_type="orchestrator", new_status=new_status)
    factory = get_session_factory()
    async with factory() as session:
        try:
            stmt = (
                update(Campaign)
                .where(Campaign.id == UUID(campaign_id))
                .values(status=new_status, updated_at=datetime.now(timezone.utc))
            )
            if only_if_current:
                stmt = stmt.where(Campaign.status.in_(only_if_current))
            r = await session.execute(stmt)
            await session.commit()
            if r.rowcount:
                log.info("campaign_state_transition", timestamp_ms=round(datetime.now(timezone.utc).timestamp() * 1000))
        except Exception as e:
            log.exception("campaign_state_transition_failed", error=str(e))


def _match_quality_score(
    offered_date_str: str,
    offered_time_str: str,
    rating: float,
    distance_km: float,
    ref_max_distance_km: float = 30.0,
) -> float:
    """Earliest 50%, Rating 30%, Proximity 20%. Normalized to 0..1."""
    try:
        from datetime import datetime as dt
        d = dt.strptime(offered_date_str + " " + offered_time_str, "%Y-%m-%d %H:%M")
        hours_until = (d - dt.now()).total_seconds() / 3600.0
        hours_until = max(0, min(hours_until, 24 * 14))  # cap 14 days
        earliest = 1.0 - (hours_until / (24 * 14))
    except Exception:
        earliest = 0.5
    rating_norm = rating / 5.0
    proximity = 1.0 - min(distance_km / ref_max_distance_km, 1.0)
    return WEIGHT_EARLIEST * earliest + WEIGHT_RATING * rating_norm + WEIGHT_PROXIMITY * proximity


def _default_target_date() -> str:
    """Return a sensible upcoming date (YYYY-MM-DD) so the agent never uses past years."""
    from datetime import date as dt_date
    d = dt_date.today() + timedelta(days=1)
    return d.isoformat()


async def _run_call_agent(
    campaign_id: str,
    call_task_id: UUID,
    provider: Provider,
    dial_phone: str,
    event_type: str = "orchestrator",
    *,
    user_id: str = "",
    service_type: str = "dentist appointment",
    target_time: str | None = None,
    target_date: str | None = None,
    tz_str: str | None = None,
) -> None:
    """
    Single call agent task (RFC 3.2 Phase 2). Triggers ElevenLabs outbound call (Twilio),
    then updates call_task in DB. MOCK_HUMAN: dial_phone is already TARGET_PHONE_NUMBER.
    """
    log = logger.bind(campaign_id=campaign_id, call_task_id=str(call_task_id), event_type=event_type)
    settings = get_settings()
    agent_id = settings.ELEVENLABS_AGENT_ID or settings.ELEVENLABS_VOICE_ID
    agent_phone_number_id = settings.ELEVENLABS_AGENT_PHONE_NUMBER_ID

    # ElevenLabs: POST /v1/convai/twilio/outbound-call to make the phone ring
    if not (agent_id and agent_phone_number_id and dial_phone):
        if not agent_phone_number_id:
            log.warning(
                "elevenlabs_outbound_skipped",
                reason="ELEVENLABS_AGENT_PHONE_NUMBER_ID not set; add it in .env to place real calls",
            )
        elif not dial_phone:
            log.warning("elevenlabs_outbound_skipped", reason="no dial_phone")
        else:
            log.warning("elevenlabs_outbound_skipped", reason="ELEVENLABS_AGENT_ID or ELEVENLABS_VOICE_ID not set")
    else:
        try:
            async with httpx.AsyncClient(timeout=ELEVENLABS_OUTBOUND_TIMEOUT) as client:
                r = await client.post(
                    "https://api.elevenlabs.io/v1/convai/twilio/outbound-call",
                    headers={"xi-api-key": settings.ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                    json={
                        "agent_id": agent_id,
                        "agent_phone_number_id": agent_phone_number_id,
                        "to_number": dial_phone,
                        "conversation_initiation_client_data": {
                            "dynamic_variables": {
                                "campaign_id": campaign_id,
                                "call_task_id": str(call_task_id),
                                "user_id": user_id,
                                "brain_instructions": ELEVENLABS_BRAIN_INSTRUCTIONS,
                                "service_type": service_type,
                                "target_time": target_time or "as soon as possible",
                                "target_date": target_date or _default_target_date(),
                                "timezone": tz_str or "America/Los_Angeles",
                            },
                        },
                    },
                )
                if r.status_code >= 400:
                    log.warning("elevenlabs_outbound_failed", status=r.status_code, body=r.text)
                else:
                    log.info("elevenlabs_outbound_ok", status=r.status_code)
        except httpx.TimeoutException:
            log.warning("elevenlabs_outbound_timeout", timeout_sec=ELEVENLABS_OUTBOUND_TIMEOUT)
        except Exception as e:
            log.exception("elevenlabs_outbound_error", error=str(e))

    factory = get_session_factory()
    async with factory() as session:
        try:
            await session.execute(
                update(CallTask).where(CallTask.id == call_task_id).values(
                    status="ringing",
                    started_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            await _transition_campaign_status(campaign_id, "negotiating", only_if_current=["dialing"])
        except Exception as e:
            log.exception("call_agent_update_failed", error=str(e))
            return
    # Simulate negotiation: after a short delay, "offer" first slot and set score
    await asyncio.sleep(0.5)
    slot = provider.available_slots[0] if provider.available_slots else None
    if not slot:
        return
    distance_km = provider.distance_km if provider.distance_km is not None else 5.0
    score = _match_quality_score(slot.date, slot.time, provider.rating, distance_km)
    async with factory() as session:
        try:
            from datetime import time as dt_time
            hour, minute = int(slot.time[:2]), int(slot.time[3:5])
            t = dt_time(hour, minute)
            from datetime import date as dt_date
            d = dt_date.fromisoformat(slot.date)
            await session.execute(
                update(CallTask).where(CallTask.id == call_task_id).values(
                    status="slot_offered",
                    offered_date=d,
                    offered_time=t,
                    offered_duration_min=slot.duration_min,
                    offered_doctor=slot.doctor,
                    score=round(score, 4),
                    distance_km=distance_km,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            await _transition_campaign_status(campaign_id, "ranking", only_if_current=["dialing", "negotiating"])
        except Exception as e:
            log.exception("call_agent_offer_failed", error=str(e))


async def create_campaign_and_swarm(
    orchestrator: SwarmOrchestrator, request: CampaignRequest, user_id: str
) -> SwarmPlan:
    """
    Create campaign in DB, spawn 15 (or MOCK_HUMAN_MAX_CALLS) call-agent tasks, return SwarmPlan.
    user_id: authenticated user UUID (from session). RFC 3.1 state machine; RFC 3.2, 3.5.
    """
    factory = get_session_factory()
    async with factory() as session:
        campaign = Campaign(
            user_id=UUID(user_id),
            status="created",
            service_type="general",
            query_text=request.prompt,
            location_lat=37.7749,
            location_lng=-122.4194,
            max_radius_km=10.0,
            weight_time=WEIGHT_EARLIEST,
            weight_rating=WEIGHT_RATING,
            weight_distance=WEIGHT_PROXIMITY,
        )
        session.add(campaign)
        await session.flush()
        campaign_id = str(campaign.id)
        await session.commit()

    logger.info(
        "campaign_created",
        campaign_id=campaign_id,
        event_type="orchestrator",
        timestamp_ms=round(datetime.now(timezone.utc).timestamp() * 1000),
    )
    await _transition_campaign_status(campaign_id, "provider_lookup")

    intent = await orchestrator._analyze_intent(request.prompt, request.user_location)
    logger.info("intent_analyzed", intent=intent.model_dump(), campaign_id=campaign_id, event_type="orchestrator")

    settings = get_settings()
    location = intent.location_query or request.user_location
    provider_svc = get_provider_service()
    origin_lat, origin_lng = 37.7749, -122.4194
    if location:
        coords = await provider_svc.geocode(location)
        if coords:
            origin_lat, origin_lng = coords
    tz = await provider_svc.get_timezone(origin_lat, origin_lng)
    if tz:
        intent = intent.model_copy(update={"timezone": tz})
    providers = await provider_svc.search_providers(
        intent.service_type,
        location,
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        limit=MAX_CALL_AGENTS_LIVE,
    )
    if not providers:
        providers = _providers_15_fallback(intent.service_type, location)
    if settings.NEXUS_MODE == "mock_human":
        target_list = settings.get_target_phones()
        if not target_list:
            raise ValueError("TARGET_PHONE_NUMBER or TARGET_PHONE_NUMBERS required when NEXUS_MODE=mock_human")
        n_tasks = min(settings.MOCK_HUMAN_MAX_CALLS, len(providers), len(target_list))
        logger.info("mock_human_targets", target_count=len(target_list), n_tasks=n_tasks, campaign_id=campaign_id, event_type="orchestrator")
    else:
        n_tasks = min(MAX_CALL_AGENTS_LIVE, len(providers))
        target_list = []

    providers = providers[:n_tasks]
    logger.info("providers_found", providers_found=len(providers), campaign_id=campaign_id, event_type="orchestrator")

    async with factory() as session:
        await session.execute(
            update(Campaign)
            .where(Campaign.id == UUID(campaign_id))
            .values(
                status="dialing",
                service_type=intent.service_type,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.flush()
        call_tasks_list: list[CallTask] = []
        for i, p in enumerate(providers):
            phone = target_list[i % len(target_list)] if settings.NEXUS_MODE == "mock_human" else p.phone
            ct = CallTask(
                campaign_id=UUID(campaign_id),
                provider_id=p.id,
                provider_name=p.name,
                provider_phone=phone,
                provider_rating=p.rating,
                distance_km=p.distance_km if p.distance_km is not None else 5.0,
                travel_time_min=p.travel_time_min,
                status="pending",
            )
            session.add(ct)
            call_tasks_list.append(ct)
        await session.commit()

    logger.info(
        "campaign_dialing",
        campaign_id=campaign_id,
        call_tasks=len(call_tasks_list),
        event_type="orchestrator",
        timestamp_ms=round(datetime.now(timezone.utc).timestamp() * 1000),
    )

    for i, ct in enumerate(call_tasks_list):
        provider = next((x for x in providers if x.id == ct.provider_id), None)
        if not provider:
            continue
        phone = target_list[i % len(target_list)] if settings.NEXUS_MODE == "mock_human" else provider.phone
        asyncio.create_task(
            _run_call_agent(
                campaign_id,
                ct.id,
                provider,
                phone,
                user_id=user_id,
                service_type=intent.service_type or "dentist appointment",
                target_time=intent.target_time,
                target_date=intent.target_date,
                tz_str=intent.timezone,
            ),
            name=f"call_agent_{ct.id}",
        )

    return SwarmPlan(campaign_id=campaign_id, intent=intent, providers=providers)


class SwarmOrchestrator:
    """Phase 1: intent analysis. create_campaign_and_swarm does DB + spawn tasks."""

    def __init__(self, openai_client: AsyncOpenAI) -> None:
        self._client = openai_client

    async def create_swarm_plan(self, request: CampaignRequest) -> SwarmPlan:
        """Legacy: plan only, no DB. Prefer create_campaign_and_swarm for full flow."""
        intent = await self._analyze_intent(request.prompt, request.user_location)
        location = intent.location_query or request.user_location
        provider_svc = get_provider_service()
        origin_lat, origin_lng = 37.7749, -122.4194
        if location:
            coords = await provider_svc.geocode(location)
            if coords:
                origin_lat, origin_lng = coords
        tz = await provider_svc.get_timezone(origin_lat, origin_lng)
        if tz:
            intent = intent.model_copy(update={"timezone": tz})
        providers = await provider_svc.search_providers(
            intent.service_type, location, origin_lat=origin_lat, origin_lng=origin_lng, limit=MAX_CALL_AGENTS_LIVE
        )
        if not providers:
            providers = _providers_15_fallback(intent.service_type, location)
        return SwarmPlan(intent=intent, providers=providers[:MAX_CALL_AGENTS_LIVE])

    async def _analyze_intent(self, prompt: str, user_location: str) -> CampaignIntent:
        system = (
            "You extract ALL booking details from the user's message so we have date, time, location. "
            "Respond ONLY with a single JSON object. No markdown. "
            "Fields: service_type (required, e.g. dentist, mechanic, hairdresser), "
            "target_date (YYYY-MM-DD or null if not specified or ASAP), "
            "target_time (morning|afternoon|evening|any or specific HH:MM 24h or null), "
            "urgency (string or null), "
            "location_query (city, area, address, or 'near me' / user_location; null only if no location given). "
            "Infer concrete date when user says 'tomorrow', 'next Friday', etc. Infer time when user says '10am', '3pm'. Use user_location when they say 'near me' or don't specify a place."
        )
        user = f"User location: {user_location}\n\nUser message: {prompt}"
        response = await self._client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = response.choices[0].message.content or ""
        if not raw.strip():
            raise ValueError("LLM returned empty intent JSON")
        data: dict[str, Any] = json.loads(raw.strip())
        target_date = data.get("target_date")
        if target_date and isinstance(target_date, str):
            try:
                from datetime import date as dt_date
                parsed = dt_date.fromisoformat(target_date.strip()[:10])
                if parsed < dt_date.today():
                    target_date = None
            except (ValueError, TypeError):
                pass
        return CampaignIntent(
            service_type=data.get("service_type", "").strip() or "general",
            target_date=target_date,
            target_time=data.get("target_time"),
            urgency=data.get("urgency"),
            location_query=data.get("location_query"),
            timezone=None,
        )


async def run_campaign_stale_monitor() -> None:
    """
    RFC 3.1: Background monitor. If a campaign stays in DIALING or NEGOTIATING for more than
    5 minutes without update, set it to FAILED and release all holds.
    """
    log = logger.bind(event_type="orchestrator", component="stale_monitor")
    threshold = datetime.now(timezone.utc) - timedelta(minutes=CAMPAIGN_STALE_MINUTES)
    factory = get_session_factory()
    appointment_svc = get_appointment_service()
    async with factory() as session:
        r = await session.execute(
            select(Campaign).where(
                Campaign.status.in_(["dialing", "negotiating"]),
                Campaign.updated_at < threshold,
            )
        )
        stale = list(r.scalars().all())
    for campaign in stale:
        campaign_id = str(campaign.id)
        log.info("campaign_stale_failing", campaign_id=campaign_id, timestamp_ms=round(datetime.now(timezone.utc).timestamp() * 1000))
        await _transition_campaign_status(campaign_id, "failed", only_if_current=["dialing", "negotiating"])
        async with factory() as session:
            r2 = await session.execute(select(CallTask).where(CallTask.campaign_id == campaign.id))
            tasks = r2.scalars().all()
        hold_keys: list[str] = []
        for ct in tasks:
            hold_keys.extend(ct.hold_keys or [])
        if hold_keys:
            await appointment_svc.release_holds_for_campaign(hold_keys, campaign_id_for_log=campaign_id)
        async with factory() as session:
            await session.execute(
                update(Campaign).where(Campaign.id == campaign.id).values(updated_at=datetime.now(timezone.utc))
            )
            await session.commit()


async def campaign_stale_monitor_loop() -> None:
    """Run stale campaign monitor every CAMPAIGN_MONITOR_INTERVAL_SECONDS."""
    while True:
        try:
            await run_campaign_stale_monitor()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("campaign_stale_monitor_error", error=str(e), event_type="orchestrator")
        await asyncio.sleep(CAMPAIGN_MONITOR_INTERVAL_SECONDS)
