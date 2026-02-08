import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, MapPin, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { extractEntities } from "../lib/entityExtract";
import { useUserProfile } from "../context/UserProfileContext";
import type { SwarmPlan } from "../types/api";

function getGreeting() {
  const h = new Date().getHours();
  return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
}

export function Dashboard() {
  const navigate = useNavigate();
  const { profile } = useUserProfile();
  const [prompt, setPrompt] = useState("");
  const [userLocation, setUserLocation] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const entities = useMemo(() => extractEntities(prompt), [prompt]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const p = prompt.trim();
    const loc = userLocation.trim() || "Boston, MA";
    if (!p) {
      setError("Please describe what you'd like to book.");
      return;
    }
    setLoading(true);
    try {
      const plan = await api<SwarmPlan>("/api/campaigns", {
        method: "POST",
        body: { prompt: p, user_location: loc },
      });
      const cid = plan.campaign_id;
      if (cid) {
        navigate(`/campaigns/${cid}`);
      } else {
        setError("Campaign created but no ID returned. Check backend.");
      }
    } catch (err) {
      const e = err as Error & { status?: number };
      if (e.status === 401) {
        setError("Session expired or not logged in.");
      } else if (e.status === 504 || e.status === 502 || e.status === 503) {
        setError("Service temporarily unavailable. Please retry.");
      } else {
        setError(e.message || "Something went wrong.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="mx-auto max-w-2xl space-y-8"
    >
      {/* Page title and greeting */}
      <header className="space-y-1">
        <p className="text-sm font-medium text-muted-foreground">
          Good {getGreeting()}, {profile.displayName}
        </p>
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Sparkles className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              What would you like to book?
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Describe your appointment and we'll call providers for you.
            </p>
          </div>
        </div>
      </header>

      {/* Command form */}
      <form onSubmit={handleSubmit} className="space-y-5">
        <section className="tile space-y-4 p-5 sm:p-6" aria-label="Booking request">
          <div className="space-y-2">
            <label htmlFor="prompt" className="block text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Your request
            </label>
            <textarea
              id="prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g., Find a dentist in Boston for tomorrow morning..."
              className="h-32 w-full resize-none rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              disabled={loading}
              aria-describedby={entities.length > 0 ? "entities" : undefined}
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="location" className="block text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Your location
            </label>
            <div className="relative">
              <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input
                id="location"
                type="text"
                value={userLocation}
                onChange={(e) => setUserLocation(e.target.value)}
                placeholder="Optional if already mentioned above"
                className="w-full rounded-lg border border-border bg-background py-2.5 pl-10 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                disabled={loading}
              />
            </div>
          </div>
          {entities.length > 0 && (
            <div id="entities" className="rounded-lg bg-muted/50 px-3 py-2.5">
              <p className="text-xs font-medium text-muted-foreground">
                {entities.length} {entities.length === 1 ? "entity" : "entities"} detected
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <AnimatePresence>
                  {entities.map((ent, i) => (
                    <motion.span
                      key={`${ent.label}-${ent.value}`}
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ delay: i * 0.04 }}
                      className="inline-flex rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
                    >
                      {ent.label}: {ent.value}
                    </motion.span>
                  ))}
                </AnimatePresence>
              </div>
            </div>
          )}
        </section>

        {error && (
          <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-primary text-base font-semibold text-primary-foreground shadow-sm transition-opacity hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50"
        >
          {loading ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
              Creating campaign…
            </>
          ) : (
            <>
              <Sparkles className="h-5 w-5" aria-hidden />
              Initiate swarm
            </>
          )}
        </button>
      </form>

      {/* Tips */}
      <section className="grid gap-4 sm:grid-cols-3" aria-label="Tips">
        <div className="tile p-4 text-left">
          <p className="font-semibold text-foreground text-sm">Be specific</p>
          <p className="mt-1 text-xs text-muted-foreground">Include date, time, and provider type.</p>
        </div>
        <div className="tile p-4 text-left">
          <p className="font-semibold text-foreground text-sm">Add location</p>
          <p className="mt-1 text-xs text-muted-foreground">Helps find nearby providers.</p>
        </div>
        <div className="tile p-4 text-left">
          <p className="font-semibold text-foreground text-sm">Set urgency</p>
          <p className="mt-1 text-xs text-muted-foreground">Use “ASAP” or “urgent” if needed.</p>
        </div>
      </section>
    </motion.div>
  );
}
