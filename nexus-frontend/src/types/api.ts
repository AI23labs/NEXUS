/** API types aligned with NEXUS backend (RFC / Appendix A). */

export type CampaignStatus =
  | "created"
  | "provider_lookup"
  | "dialing"
  | "negotiating"
  | "ranking"
  | "confirmed"
  | "failed"
  | "cancelled";

export interface CampaignIntent {
  service_type: string;
  target_date: string | null;
  target_time: string | null;
  urgency: string | null;
  location_query: string | null;
  timezone: string | null;
}

export interface ProviderLocation {
  lat: number;
  lng: number;
}

export interface Provider {
  id: string;
  name: string;
  phone: string;
  rating: number;
  address: string;
  available_slots: Array<{ date: string; time: string; duration_min: number; doctor?: string }>;
  distance_km?: number;
  travel_time_min?: number;
  type?: string;
  location?: ProviderLocation;
}

export interface SwarmPlan {
  campaign_id: string | null;
  intent: CampaignIntent;
  providers: Provider[];
}

export interface Campaign {
  id: string;
  user_id: string;
  status: CampaignStatus;
  service_type: string;
  query_text: string;
  created_at: string | null;
  updated_at: string | null;
  confirmed_call_task_id: string | null;
}

export interface CallTask {
  id: string;
  campaign_id: string;
  provider_id: string | null;
  provider_name: string | null;
  provider_phone: string | null;
  status: string;
  score: number | null;
  offered_date: string | null;
  offered_time: string | null;
  offered_duration_min: number | null;
  offered_doctor: string | null;
  hold_keys: string[];
  started_at: string | null;
  ended_at: string | null;
  updated_at: string | null;
  /** Optional for Best Matches UI — mock or from Places API */
  photo_url?: string | null;
  address?: string | null;
  lat?: number | null;
  lng?: number | null;
}

export interface StreamEvent {
  campaign_id: string;
  campaign_status: CampaignStatus;
  updated_at: string | null;
  call_tasks: CallTask[];
  error?: string;
}

export interface CampaignResults {
  campaign_id: string;
  offers: CallTask[];
}

export interface ConfirmResponse {
  status: "confirmed";
  call_task_id: string;
  calendar_synced: boolean;
  message: string;
}

export interface CancelResponse {
  status: "cancelled";
  message: string;
}

export interface Appointment {
  id: string;
  campaign_id: string;
  call_task_id: string;
  user_id: string;
  provider_id: string;
  provider_name: string;
  provider_phone: string;
  appointment_date: string;
  appointment_time: string;
  duration_min: number;
  doctor_name: string | null;
  calendar_synced: boolean;
  status: string;
  created_at: string | null;
  /** Optional for "View in Google" — built client-side if backend doesn't provide */
  calendar_link?: string | null;
}

export interface AppointmentsResponse {
  appointments: Appointment[];
}

export interface ApiErrorBody {
  detail: string | { msg?: string }[];
}
