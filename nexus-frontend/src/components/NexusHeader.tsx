import { useState, useRef, useEffect } from "react";
import { Link, NavLink } from "react-router-dom";
import { LayoutDashboard, Calendar, Settings, Moon, Sun, LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useUserProfile } from "../context/UserProfileContext";
import { useAuditTrail } from "../context/AuditTrailContext";
import { AuditTrailSidebar } from "./AuditTrailSidebar";


export function NexusHeader() {
  const [userOpen, setUserOpen] = useState(false);
  const userRef = useRef<HTMLDivElement>(null);
  const { authState, isLoggedIn, logout } = useAuth();
  const { theme, toggle: toggleTheme } = useTheme();
  const { profile } = useUserProfile();
  const { toggle: toggleAudit } = useAuditTrail();

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserOpen(false);
    }
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, []);

  return (
    <>
      <AuditTrailSidebar />
      <header className="sticky top-0 z-30 border-b border-border bg-card">
        <div className="mx-auto max-w-7xl px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-8">
              <Link to="/" className="text-xl font-bold text-primary">
                N.E.X.U.S.
              </Link>
              <p className="hidden text-xs uppercase tracking-widest text-muted-foreground sm:block">
                Network for ElevenLabs X-call User Scheduling
              </p>
              {isLoggedIn && (
                <nav className="flex items-center gap-1">
                  <NavLink
                    to="/"
                    end
                    className={({ isActive }) =>
                      `flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                        isActive
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`
                    }
                  >
                    <LayoutDashboard className="h-4 w-4" />
                    My Swarm
                  </NavLink>
                  <NavLink
                    to="/appointments"
                    className={({ isActive }) =>
                      `flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                        isActive
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`
                    }
                  >
                    <Calendar className="h-4 w-4" />
                    My Appointments
                  </NavLink>
                  <Link
                    to="/admin"
                    className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    Admin Analytics
                  </Link>
                  <button
                    type="button"
                    onClick={toggleAudit}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-primary hover:bg-primary/10"
                  >
                    Audit Trail
                  </button>
                </nav>
              )}
            </div>
            {isLoggedIn && (
              <div className="flex items-center gap-4">
                <div className="hidden gap-6 text-xs text-muted-foreground sm:flex">
                  <span>ACTIVE CALLS 11</span>
                  <span>SOFT-LOCKS 10</span>
                  <span>WAITLIST 0</span>
                  <span>LATENCY 347ms</span>
                </div>
                <div className="relative" ref={userRef}>
                  <button
                    type="button"
                    onClick={() => setUserOpen((o) => !o)}
                    className="flex items-center gap-2 rounded-lg px-2 py-1.5 font-medium text-foreground hover:bg-muted"
                  >
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-primary font-semibold">
                      {profile.displayName.charAt(0).toUpperCase()}
                    </span>
                    <span className="hidden sm:inline">{profile.displayName}</span>
                  </button>
                  {userOpen && (
                    <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded-xl border border-border bg-card py-1 shadow-lg">
                      <div className="border-b border-border px-3 py-2">
                        <p className="font-medium text-foreground text-sm">{profile.displayName}</p>
                        <p className="text-muted-foreground text-xs">Signed in with Google</p>
                      </div>
                      <Link
                        to="/settings"
                        className="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted"
                        onClick={() => setUserOpen(false)}
                      >
                        <Settings className="h-4 w-4" />
                        Settings
                      </Link>
                      <button
                        type="button"
                        onClick={() => {
                          toggleTheme();
                          setUserOpen(false);
                        }}
                        className="flex w-full items-center justify-between px-3 py-2 text-sm text-foreground hover:bg-muted"
                      >
                        <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
                        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          logout();
                          setUserOpen(false);
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-muted"
                      >
                        <LogOut className="h-4 w-4" />
                        Log out
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
            {authState !== "loading" && !isLoggedIn && (
              <Link
                to="/auth"
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
              >
                Sign in
              </Link>
            )}
          </div>
        </div>
      </header>
    </>
  );
}
