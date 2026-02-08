import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useUserProfile } from "../context/UserProfileContext";
import { useTheme } from "../context/ThemeContext";

export function Settings() {
  const { profile, updateProfile } = useUserProfile();
  const { theme } = useTheme();
  const [displayName, setDisplayName] = useState(profile.displayName);
  const [phone, setPhone] = useState(profile.phone);
  const [homeAddress, setHomeAddress] = useState(profile.homeAddress);
  const [preferHighlyRated, setPreferHighlyRated] = useState(profile.preferHighlyRated);

  useEffect(() => {
    setDisplayName(profile.displayName);
    setPhone(profile.phone);
    setHomeAddress(profile.homeAddress);
    setPreferHighlyRated(profile.preferHighlyRated);
  }, [profile]);

  function handleSave() {
    updateProfile({ displayName, phone, homeAddress, preferHighlyRated });
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="mt-0.5 text-xs uppercase tracking-widest text-muted-foreground">
          Profile & preferences
        </p>
      </div>

      <section className="tile space-y-4 p-4">
        <h2 className="font-semibold text-foreground">User profile</h2>
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Display name</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Phone number</label>
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+1 555 000 0000"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Home address</label>
          <input
            type="text"
            value={homeAddress}
            onChange={(e) => setHomeAddress(e.target.value)}
            placeholder="Boston, MA or Brookline"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <p className="mt-1 text-xs text-muted-foreground">Used for distance calculations.</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="prefer"
            checked={preferHighlyRated}
            onChange={(e) => setPreferHighlyRated(e.target.checked)}
            className="rounded border-border text-primary focus:ring-primary"
          />
          <label htmlFor="prefer" className="text-sm text-foreground">
            Prefer highly rated over closest
          </label>
        </div>
        <button
          type="button"
          onClick={handleSave}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Save
        </button>
      </section>

      <section className="tile p-4">
        <h2 className="font-semibold text-foreground">Appearance</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Theme: <span className="font-medium text-foreground">{theme === "dark" ? "Dark" : "Light"}</span>. Toggle from the user menu (top right).
        </p>
      </section>

      <section className="tile p-4">
        <h2 className="font-semibold text-foreground">Demo mode</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          NEXUS is connected to the live backend. Use Admin Analytics to view system health and mock metrics.
        </p>
      </section>
    </motion.div>
  );
}
