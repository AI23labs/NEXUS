import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Calendar } from "lucide-react";
import { api } from "../lib/api";
import { useAuditTrail } from "../context/AuditTrailContext";
import { buildGoogleCalendarLink } from "../lib/calendarLink";
import type { AppointmentsResponse, Appointment } from "../types/api";

function AppointmentCard({
  a,
  showSyncedBadge,
  onOpenTranscript,
}: {
  a: Appointment;
  showSyncedBadge: boolean;
  onOpenTranscript: () => void;
}) {
  const calendarUrl = buildGoogleCalendarLink(
    a.provider_name,
    a.appointment_date,
    a.appointment_time,
    a.duration_min
  );

  return (
    <li className="tile p-4">
      <div className="font-semibold text-foreground">{a.provider_name}</div>
      <div className="mt-1 text-sm text-muted-foreground">
        {a.appointment_date} at {a.appointment_time} · {a.duration_min} min
        {a.doctor_name && ` · ${a.doctor_name}`}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {a.calendar_synced && (
          <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 ${showSyncedBadge ? "animate-pulse" : ""}`}>
            Added to Calendar
          </span>
        )}
        <a href={calendarUrl} target="_blank" rel="noopener noreferrer" className="text-primary text-xs font-medium hover:underline">
          View in Google
        </a>
        <button type="button" onClick={onOpenTranscript} className="text-orange-500 text-xs font-medium hover:underline">
          Transcript
        </button>
      </div>
    </li>
  );
}

function CalendarDayView({ appointments, onOpenTranscript }: { appointments: Appointment[]; onOpenTranscript: () => void }) {
  const byDate: Record<string, Appointment[]> = {};
  appointments.forEach((a) => {
    const d = a.appointment_date;
    if (!byDate[d]) byDate[d] = [];
    byDate[d].push(a);
  });
  const dates = Object.keys(byDate).sort();
  if (dates.length === 0) return null;

  return (
    <div className="space-y-4">
      {dates.map((date) => (
        <div key={date}>
          <h3 className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">{date}</h3>
          <ul className="space-y-2">
            {byDate[date].map((a) => (
              <AppointmentCard key={a.id} a={a} showSyncedBadge={a.calendar_synced} onOpenTranscript={onOpenTranscript} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function Appointments() {
  const [searchParams] = useSearchParams();
  const view = searchParams.get("view") === "calendar" ? "calendar" : "list";
  const [data, setData] = useState<AppointmentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { open: openAudit } = useAuditTrail();
  const openTranscript = () => openAudit();

  useEffect(() => {
    api<AppointmentsResponse>("/api/appointments")
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="h-10 w-10 rounded-full border-2 border-slate-200 border-t-electric animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-8 text-center">
        <p className="text-destructive mb-4">{error}</p>
        <Link to="/" className="text-primary hover:underline">Back to dashboard</Link>
      </div>
    );
  }

  const appointments = data?.appointments ?? [];

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">My Appointments</h1>
          <p className="mt-0.5 text-xs uppercase tracking-widest text-muted-foreground">
            Network for ElevenLabs X-call User Scheduling
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={view === "calendar" ? "/appointments" : "/appointments?view=calendar"}
            className="text-sm font-medium text-muted-foreground hover:text-primary"
          >
            {view === "calendar" ? "List view" : "Calendar view"}
          </Link>
          <button type="button" onClick={openAudit} className="text-primary text-sm font-medium hover:underline">
            Audit Trail
          </button>
        </div>
      </div>

      {view === "calendar" ? (
        <div>
          <CalendarDayView appointments={appointments} onOpenTranscript={openTranscript} />
          {appointments.length === 0 && (
            <div className="tile flex flex-col items-center justify-center p-12 text-center">
              <Calendar className="h-12 w-12 text-muted-foreground" />
              <p className="mt-4 text-muted-foreground">No appointments yet.</p>
              <Link to="/" className="mt-2 text-primary hover:underline">
                Create a booking request
              </Link>
            </div>
          )}
        </div>
      ) : (
        <>
          <p className="mb-6 text-muted-foreground">Confirmed bookings. Synced events show in Google Calendar.</p>
          {appointments.length === 0 ? (
            <div className="tile flex flex-col items-center justify-center p-12 text-center">
              <Calendar className="h-12 w-12 text-muted-foreground" />
              <p className="mt-4 text-muted-foreground">No appointments yet.</p>
              <Link to="/" className="mt-2 text-primary hover:underline">
                Create a booking request
              </Link>
            </div>
          ) : (
            <ul className="space-y-4">
              {appointments.map((a) => (
                <AppointmentCard key={a.id} a={a} showSyncedBadge={false} onOpenTranscript={openTranscript} />
              ))}
            </ul>
          )}
        </>
      )}
    </motion.div>
  );
}
