export type Role = "client" | "admin";
export type AppointmentStatus = "booked" | "cancelled_by_client" | "cancelled_by_admin" | "completed" | "no_show";

export interface User {
  id: string;
  telegram_id: number | null;
  name: string;
  username: string | null;
  phone: string | null;
  role: Role;
  created_at: string;
  notifications_enabled: boolean;
  privacy_accepted_at: string | null;
}

export interface Info {
  studio_name: string;
  master_name: string;
  welcome_text: string;
  address: string;
  contact_phone: string;
  contact_telegram: string;
  operator_name: string;
  operator_inn: string;
  privacy_email: string;
  timezone: string;
  currency: string;
  booking_horizon_days: number;
  cancel_min_hours: number;
  allow_client_reschedule: boolean;
}

export interface Service {
  id: string;
  name: string;
  description: string;
  duration_minutes: number;
  price_minor: number;
  currency: string;
}

export interface AdminService extends Service {
  is_active: boolean;
  sort_order: number;
  buffer_minutes: number | null;
}

export interface DateAvailability {
  date: string;
  status: "available" | "full" | "closed";
  free_slots: number;
}

export interface Slot {
  starts_at: string;
  ends_at: string;
  local_time: string;
}

export interface Appointment {
  id: string;
  service_id: string | null;
  service_name: string;
  duration_minutes: number;
  price_minor: number;
  currency: string;
  starts_at: string;
  ends_at: string;
  status: AppointmentStatus;
  comment: string | null;
  created_at: string;
  cancelled_at: string | null;
  can_cancel: boolean;
  can_reschedule: boolean;
}

export interface MyAppointments {
  upcoming: Appointment[];
  history: Appointment[];
  cancelled: Appointment[];
}

export interface ClientBrief {
  id: string;
  name: string;
  phone: string | null;
  telegram_id: number | null;
  username: string | null;
}

export interface AdminAppointment extends Appointment {
  buffer_minutes: number;
  blocked_until: string;
  client: ClientBrief;
  cancelled_by: string | null;
}

export interface HistoryItem {
  id: number;
  action: string;
  actor_role: string | null;
  old_starts_at: string | null;
  new_starts_at: string | null;
  old_status: string | null;
  new_status: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AdminAppointmentDetail extends AdminAppointment {
  history: HistoryItem[];
}

export interface AdminClient {
  id: string;
  name: string;
  username: string | null;
  telegram_id: number | null;
  phone: string | null;
  created_at: string;
  completed_count: number;
  cancelled_count: number;
  no_show_count: number;
  last_visit_at: string | null;
  upcoming_at: string | null;
  privacy_accepted_at: string | null;
  anonymized_at: string | null;
}

export interface AdminClientDetail extends AdminClient {
  admin_notes: string | null;
  is_active: boolean;
  appointments: AdminAppointment[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface TimeInterval {
  start: string;
  end: string;
}

export interface DaySchedule {
  weekday: number;
  is_working_day: boolean;
  intervals: TimeInterval[];
}

export type ExceptionType = "closed" | "open" | "break";

export interface ScheduleException {
  id: number;
  starts_at: string;
  ends_at: string;
  exception_type: ExceptionType;
  reason: string | null;
}

export interface Conflict {
  appointment_id: string;
  starts_at: string;
  ends_at: string;
  client_name: string;
  client_phone: string | null;
  service_name: string;
}

export interface Schedule {
  days: DaySchedule[];
  exceptions: ScheduleException[];
  timezone: string;
  conflicts: Conflict[];
}

export interface AdminSettings extends Info {
  default_duration_minutes: number;
  slot_step_minutes: number;
  buffer_minutes: number;
  min_lead_minutes: number;
  max_active_bookings_per_client: number;
  reminder_hours: number[];
  notify_admin_new: boolean;
  notify_admin_cancel: boolean;
  notify_admin_reschedule: boolean;
}

export interface AuditItem {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}
