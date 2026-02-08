import { motion } from "framer-motion";
import { Phone, Calendar, Zap } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const features = [
  { icon: Phone, title: "15 Parallel Calls", desc: "We call providers simultaneously so you get options fast." },
  { icon: Calendar, title: "Calendar Sync", desc: "Confirmed appointments sync to your Google Calendar." },
  { icon: Zap, title: "Instant Booking", desc: "Confirm a slot with one click; we handle the rest." },
];

export function Auth() {
  const { authState, isLoggedIn, login } = useAuth();

  if (authState === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (isLoggedIn) {
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md"
      >
        <div className="tile p-8">
          <h1 className="text-2xl font-bold text-primary">N.E.X.U.S.</h1>
          <p className="mt-1 text-xs uppercase tracking-widest text-muted-foreground">
            Network for ElevenLabs X-call User Scheduling
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            {features.map((item, i) => (
              <motion.div
                key={item.title}
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: i * 0.05 }}
                className="rounded-lg border border-border bg-muted/50 p-3 text-center"
              >
                <item.icon className="mx-auto h-6 w-6 text-primary" />
                <p className="mt-1 text-xs font-semibold text-foreground">{item.title}</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground">{item.desc}</p>
              </motion.div>
            ))}
          </div>
          <button
            type="button"
            onClick={login}
            className="mt-8 flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-3 font-semibold text-primary-foreground hover:opacity-90"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24">
              <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Sign in with Google
          </button>
          <p className="mt-6 text-center text-xs text-muted-foreground">
            Powered by ElevenLabs Voice AI
          </p>
        </div>
      </motion.div>
    </div>
  );
}
