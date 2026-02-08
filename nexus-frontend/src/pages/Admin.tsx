import { useEffect, useState } from "react";
import { motion } from "framer-motion";

type Health = { status?: string; mode?: string } | null;
type Ready = { status?: string; db?: string; redis?: string } | null;

export function Admin() {
  const [mode, setMode] = useState<"LIVE" | "MOCK_AI">("LIVE");
  const [health, setHealth] = useState<Health>(null);
  const [ready, setReady] = useState<Ready>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    const base = (import.meta.env.VITE_API_URL as string)?.trim() || "";
    const prefix = base ? `${base}` : "";
    Promise.all([
      fetch(`${prefix}/health`, { credentials: "include" }).then((r) => r.json()).catch(() => null),
      fetch(`${prefix}/ready`, { credentials: "include" }).then((r) => r.json()).catch(() => null),
    ]).then(([h, r]) => {
      setHealth(h);
      setReady(r);
      if (h?.mode) setMode(h.mode === "live" ? "LIVE" : "MOCK_AI");
    }).catch(() => setHealthError("Could not reach backend"));
  }, []);

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Admin Analytics</h1>
        <p className="mt-0.5 text-xs uppercase tracking-widest text-muted-foreground">
          Bird's-eye view · God Mode
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="tile p-4">
          <h2 className="mb-3 font-semibold text-foreground">Mode Switcher (God Mode)</h2>
          <p className="mb-3 text-sm text-muted-foreground">
            Toggle between LIVE and MOCK_AI for demo. Backend must be restarted to apply.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setMode("LIVE")}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${mode === "LIVE" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}
            >
              LIVE
            </button>
            <button
              type="button"
              onClick={() => setMode("MOCK_AI")}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${mode === "MOCK_AI" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}
            >
              MOCK_AI
            </button>
          </div>
        </section>

        <section className="tile p-4">
          <h2 className="mb-3 font-semibold text-foreground">System Health</h2>
          {healthError && <p className="text-red-600 text-sm">{healthError}</p>}
          {health && (
            <ul className="space-y-1 text-sm">
            <li>API: <span className="text-emerald-600">{health.status ?? "—"}</span></li>
            <li>Mode: <span className="text-primary">{health.mode ?? "—"}</span></li>
            </ul>
          )}
          {ready && (
            <ul className="space-y-1 text-sm mt-2">
            <li>Redis: <span className="text-emerald-600">{ready.redis ?? "—"}</span></li>
            <li>DB: <span className="text-emerald-600">{ready.db ?? "—"}</span></li>
            </ul>
          )}
        </section>
      </div>

      <section className="tile p-4">
        <h2 className="mb-3 font-semibold text-foreground">Swarm Analytics (Mock)</h2>
        <div className="grid gap-4 text-sm sm:grid-cols-3">
          <div>
            <p className="text-muted-foreground">Active calls</p>
            <p className="text-2xl font-bold text-primary">3</p>
          </div>
          <div>
            <p className="text-muted-foreground">Twilio cost (today)</p>
            <p className="text-2xl font-bold text-foreground">$0.42</p>
          </div>
          <div>
            <p className="text-muted-foreground">ElevenLabs API (min)</p>
            <p className="text-2xl font-bold text-foreground">12.4</p>
          </div>
        </div>
      </section>

      <section className="tile p-4">
        <h2 className="mb-3 font-semibold text-foreground">Active Campaigns (Mock)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="py-2 text-left text-muted-foreground">Campaign ID</th>
                <th className="py-2 text-left text-muted-foreground">Status</th>
                <th className="py-2 text-left text-muted-foreground">User</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-border">
                <td className="py-2 font-mono text-xs">…a1b2</td>
                <td className="py-2 text-primary">negotiating</td>
                <td className="py-2">Samhita</td>
              </tr>
              <tr className="border-b border-border">
                <td className="py-2 font-mono text-xs">…c3d4</td>
                <td className="py-2 text-emerald-600">confirmed</td>
                <td className="py-2">Demo</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </motion.div>
  );
}
