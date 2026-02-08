import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkles, MapPin, FileText } from "lucide-react";
import { api } from "../lib/api";
import { useCampaignStream } from "../hooks/useCampaignStream";
import { useAuditTrail } from "../context/AuditTrailContext";
import type {
  Campaign,
  CampaignResults,
  CallTask,
  ConfirmResponse,
} from "../types/api";

const STATUS_LABELS: Record<string, string> = {
  created: "Created",
  provider_lookup: "Finding providers",
  dialing: "Dialing",
  negotiating: "Negotiating",
  ranking: "Ranking",
  confirmed: "Confirmed",
  failed: "Failed",
  cancelled: "Cancelled",
};

function LockIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary shrink-0">
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function badgeClass(status: string): string {
  if (status === "confirmed" || status === "slot_offered") return "bg-emerald-500/90 text-white";
  if (status === "failed" || status === "no_answer" || status === "rejected") return "bg-destructive/90 text-white";
  return "bg-amber-500/90 text-white";
}

function getProviderPhotoUrl(o: CallTask): string {
  return o.photo_url || `https://images.unsplash.com/photo-1629909613654-28e377c37b09?w=120&h=80&fit=crop`;
}

function mapUrlForProvider(o: CallTask): string {
  const addr = o.address || (o.provider_name ? `${o.provider_name} Boston MA` : "Boston, MA");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(addr)}`;
}

export function CampaignDetail() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [campaignError, setCampaignError] = useState<string | null>(null);
  const [offers, setOffers] = useState<CallTask[] | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [confirmSuccess, setConfirmSuccess] = useState<ConfirmResponse | null>(null);
  const { open: openAudit } = useAuditTrail();

  const { data: streamData, streamError, isLive } = useCampaignStream(campaignId ?? null);
  const status = streamData?.campaign_status ?? campaign?.status;
  const callTasks = streamData?.call_tasks ?? [];

  useEffect(() => {
    if (!campaignId) return;
    api<Campaign>(`/api/campaigns/${campaignId}`)
      .then(setCampaign)
      .catch((e: Error & { status?: number }) => {
        if (e.status === 404) setCampaignError("Campaign not found.");
        else setCampaignError(e.message || "Failed to load campaign.");
      });
  }, [campaignId]);

  async function loadResults() {
    if (!campaignId) return;
    setResultsLoading(true);
    setCampaignError(null);
    try {
      const res = await api<CampaignResults>(`/api/campaigns/${campaignId}/results`);
      setOffers(res.offers ?? []);
    } catch (e) {
      const err = e as Error & { status?: number };
      if (err.status === 404) setCampaignError("Campaign not found.");
      else setCampaignError(err.message || "Failed to load results.");
    } finally {
      setResultsLoading(false);
    }
  }

  async function confirmOffer(callTaskId: string) {
    if (!campaignId) return;
    setConfirmError(null);
    setConfirmingId(callTaskId);
    try {
      const res = await api<ConfirmResponse>(`/api/campaigns/${campaignId}/confirm`, {
        method: "POST",
        body: { call_task_id: callTaskId },
      });
      setConfirmSuccess(res);
    } catch (e) {
      const err = e as Error & { status?: number };
      setConfirmError(err.message || "Confirm failed.");
    } finally {
      setConfirmingId(null);
    }
  }

  async function cancelCampaign() {
    if (!campaignId) return;
    try {
      await api(`/api/campaigns/${campaignId}/cancel`, { method: "POST" });
      setCampaign((c) => (c ? { ...c, status: "cancelled" } : null));
    } catch (e) {
      setCampaignError((e as Error).message);
    }
  }

  const canCancel = status && ["created", "provider_lookup", "dialing", "negotiating", "ranking"].includes(status);
  const winningCallTaskId = confirmSuccess?.call_task_id ?? null;
  const CONNECTED_INDEX = 0;
  const nexusSlots = Array.from({ length: 15 }, (_, i) => ({
    index: i + 1,
    task: i === CONNECTED_INDEX ? callTasks[0] : undefined,
    connected: i === CONNECTED_INDEX,
  }));

  if (campaignError && !campaign) {
    return (
      <div className="py-8 text-center">
        <p className="text-destructive mb-4">{campaignError}</p>
        <Link to="/" className="text-primary hover:underline">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="grid grid-cols-1 gap-4 lg:grid-cols-12"
    >
      <aside className="tile lg:col-span-3 p-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Sparkles className="h-4 w-4" />
          </div>
          <h2 className="font-semibold text-foreground">Command Center</h2>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">Describe your scheduling needs in natural language.</p>
        <div className="mt-3 rounded-lg border border-border bg-muted/50 p-2">
          <p className="text-[10px] uppercase text-muted-foreground">YOUR REQUEST</p>
          <p className="text-sm text-foreground">{campaign?.query_text ?? "—"}</p>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badgeClass(status ?? "")}`}>
            {STATUS_LABELS[status ?? ""] ?? status ?? "—"}
          </span>
          {isLive && (
            <span className="flex items-center gap-1 text-xs text-primary">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              Swarm Active · 15 agents negotiating appointments...
            </span>
          )}
        </div>
        {canCancel && (
          <button type="button" onClick={cancelCampaign} className="mt-2 text-xs text-destructive hover:underline">
            Cancel campaign
          </button>
        )}
        {streamError && <p className="mt-1 text-xs text-destructive">Stream: {streamError}</p>}
      </aside>

      <div className="lg:col-span-6">
        <h2 className="mb-2 text-sm font-semibold text-foreground">Live Call Tasks</h2>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          {nexusSlots.map(({ index, task, connected }, i) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.03 }}
              className={`tile p-2 text-center ${connected && task ? "ring-1 ring-primary/30" : "opacity-80"}`}
            >
              <div className="font-mono text-[10px] font-semibold text-muted-foreground">NEXUS-{String(index).padStart(2, "0")}</div>
              {task ? (
                <>
                  <div className="mt-0.5 truncate text-xs font-medium text-foreground" title={task.provider_name ?? ""}>
                    {task.provider_name ?? "—"}
                  </div>
                  <div className="mt-0.5 flex items-center justify-center gap-0.5">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badgeClass(task.status)}`}>
                      {task.status === "slot_offered" ? "CONFIRMED" : task.status.toUpperCase()}
                    </span>
                    {task.hold_keys?.length ? <LockIcon /> : null}
                  </div>
                  <button
                    type="button"
                    onClick={openAudit}
                    className="mt-1 flex w-full items-center justify-center gap-0.5 text-[10px] text-primary"
                  >
                    <FileText className="h-3 w-3" />
                    Audit
                  </button>
                  {(task.status === "slot_offered" || task.status === "negotiating") && (
                    <button
                      type="button"
                      className="mt-0.5 w-full rounded bg-primary py-0.5 text-[10px] font-medium text-primary-foreground"
                    >
                      INTERVENE
                    </button>
                  )}
                </>
              ) : (
                <div className="mt-0.5 text-[10px] text-muted-foreground">Standby</div>
              )}
            </motion.div>
          ))}
        </div>
      </div>

      <aside className="tile lg:col-span-3 p-4">
        <h2 className="font-semibold text-foreground">Best Matches</h2>
        <p className="text-muted-foreground text-xs">Ranked by distance, rating & availability.</p>
        {(status === "ranking" || offers !== null || confirmSuccess) && (
          <div className="mt-3">
            {offers === null && !confirmSuccess ? (
              <button
                type="button"
                onClick={loadResults}
                disabled={resultsLoading}
                className="w-full rounded-lg bg-primary py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {resultsLoading ? "Loading…" : "View results"}
              </button>
            ) : (offers?.length ?? 0) === 0 && !confirmSuccess ? (
              <p className="text-muted-foreground text-sm">No slots offered yet.</p>
            ) : (
              <ul className="space-y-2">
                {offers?.map((o, i) => (
                  <motion.li
                    key={o.id}
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className={`tile p-2 ${o.id === winningCallTaskId ? "ring-1 ring-primary" : ""}`}
                  >
                    <div className="flex gap-2">
                      <img
                        src={getProviderPhotoUrl(o)}
                        alt=""
                        className="h-14 w-14 shrink-0 rounded object-cover"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">{o.provider_name ?? "—"}</p>
                        <p className="text-muted-foreground text-xs">
                          {o.offered_date} {o.offered_time}
                          {o.offered_doctor && ` · ${o.offered_doctor}`}
                        </p>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {!confirmSuccess && (
                            <button
                              type="button"
                              onClick={() => confirmOffer(o.id)}
                              disabled={!!confirmingId}
                              className="rounded bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                            >
                              {confirmingId === o.id ? "Confirming…" : "Confirm & Book"}
                            </button>
                          )}
                          <a
                            href={mapUrlForProvider(o)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-0.5 rounded border border-border px-2 py-0.5 text-xs text-primary"
                          >
                            <MapPin className="h-3 w-3" />
                            Show on Map
                          </a>
                        </div>
                      </div>
                      {o.score != null && (
                        <span className="text-primary text-xs font-semibold">{Math.round(o.score)} pts</span>
                      )}
                    </div>
                  </motion.li>
                ))}
              </ul>
            )}
            {confirmError && <p className="mt-2 text-destructive text-xs">{confirmError}</p>}
            {confirmSuccess && (
              <p className="mt-2 text-sm text-emerald-600 dark:text-emerald-400">
                Confirmed.
                {confirmSuccess.calendar_synced && " Added to Google Calendar."}
                <Link to="/appointments" className="ml-1 text-primary underline">My Appointments</Link>
              </p>
            )}
          </div>
        )}
      </aside>
    </motion.div>
  );
}
