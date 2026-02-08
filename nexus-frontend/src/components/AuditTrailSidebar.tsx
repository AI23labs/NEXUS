import { useAuditTrail } from "../context/AuditTrailContext";

/** Mock tool calls for demo — orange highlights for [Tool Calls] */
const MOCK_ENTRIES = [
  { type: "tool", msg: "[Tool Call] check_availability — date: 2025-02-11, time: 15:00" },
  { type: "tool", msg: "[Tool Call] report_slot_offered — provider: Smile Dental, slot held" },
  { type: "tool", msg: "[Tool Call] get_distance — 2.3 km, 8 min" },
  { type: "text", msg: "Agent: I have a slot at 3 PM next Tuesday. Shall I book it?" },
  { type: "tool", msg: "[Tool Call] book_slot — confirmed, calendar_synced" },
  { type: "text", msg: "Agent: Booking confirmed. Added to your Google Calendar." },
];

export function AuditTrailSidebar() {
  const { isOpen, close } = useAuditTrail();

  if (!isOpen) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/20 dark:bg-black/40 z-40"
        onClick={close}
        aria-hidden
      />
      <aside
        className="tile fixed top-0 right-0 z-50 flex h-full w-80 max-w-[90vw] flex-col border-l border-border"
        aria-label="Audit Trail"
      >
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="font-semibold text-foreground">Audit Trail</h2>
          <button type="button" onClick={close} className="p-1 text-muted-foreground hover:text-foreground" aria-label="Close">
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-auto p-3">
          <p className="mb-3 text-xs uppercase tracking-wider text-muted-foreground">Brain — Tool Calls</p>
          <ul className="space-y-2 font-mono text-xs text-foreground">
            {MOCK_ENTRIES.map((e, i) => (
              <li key={i} className="leading-relaxed">
                {e.type === "tool" ? (
                  <span className="font-medium text-orange-500">{e.msg}</span>
                ) : (
                  <span className="text-muted-foreground">{e.msg}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </>
  );
}
