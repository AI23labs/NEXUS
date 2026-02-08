import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

const STORAGE_KEY = "nexus-user-profile";

export interface UserProfile {
  displayName: string;
  phone: string;
  homeAddress: string;
  preferHighlyRated: boolean;
}

const defaultProfile: UserProfile = {
  displayName: "Samhita",
  phone: "",
  homeAddress: "",
  preferHighlyRated: true,
};

function loadProfile(): UserProfile {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<UserProfile>;
      return { ...defaultProfile, ...parsed };
    }
  } catch {
    // ignore
  }
  return { ...defaultProfile };
}

function saveProfile(p: UserProfile) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    // ignore
  }
}

interface UserProfileContextValue {
  profile: UserProfile;
  updateProfile: (partial: Partial<UserProfile>) => void;
}

const UserProfileContext = createContext<UserProfileContextValue | null>(null);

export function UserProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<UserProfile>(loadProfile);

  const updateProfile = useCallback((partial: Partial<UserProfile>) => {
    setProfile((prev) => {
      const next = { ...prev, ...partial };
      saveProfile(next);
      return next;
    });
  }, []);

  return (
    <UserProfileContext.Provider value={{ profile, updateProfile }}>
      {children}
    </UserProfileContext.Provider>
  );
}

export function useUserProfile(): UserProfileContextValue {
  const ctx = useContext(UserProfileContext);
  if (!ctx) throw new Error("useUserProfile must be used within UserProfileProvider");
  return ctx;
}
