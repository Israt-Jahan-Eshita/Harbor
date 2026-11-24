export type Locale = "bn" | "en";

export interface ApiErrorShape {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;
  requestId: string | null;

  constructor(
    code: string,
    message: string,
    status: number,
    details: Record<string, unknown> = {},
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
  }
}

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

if (
  typeof window !== "undefined" &&
  process.env.NODE_ENV === "production" &&
  !process.env.NEXT_PUBLIC_API_URL &&
  window.location.hostname !== "localhost" &&
  window.location.hostname !== "127.0.0.1"
) {
  console.error(
    "[Harbor] NEXT_PUBLIC_API_URL was not set at build time; requests are defaulting to http://localhost:8000.",
  );
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  token?: string | null;
  locale?: Locale;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { body, token, locale = "bn", headers, ...rest } = options;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  const requestHeaders = new Headers(headers);
  requestHeaders.set("Accept-Language", locale);
  if (token) {
    requestHeaders.set("Authorization", `Bearer ${token}`);
  }
  if (body !== undefined && !isFormData && !requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${normalizedPath}`, {
      ...rest,
      headers: requestHeaders,
      body:
        body === undefined
          ? undefined
          : isFormData
            ? (body as FormData)
            : JSON.stringify(body),
    });
  } catch (err) {
    throw new ApiError(
      "NETWORK_ERROR",
      err instanceof Error ? err.message : "Network request failed",
      0,
      {},
      null,
    );
  }

  const requestId = response.headers.get("X-Request-Id");
  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await response.json().catch(() => null) : null;

  if (!response.ok) {
    const errObj = payload as Partial<ApiErrorShape> | null;
    throw new ApiError(
      errObj?.code || `HTTP_${response.status}`,
      errObj?.message || response.statusText || "Request failed",
      response.status,
      errObj?.details || {},
      requestId,
    );
  }

  return payload as T;
}

/* ---------- Common & Household Contracts ---------- */

export interface HealthResponse {
  status: string;
  db: string;
}

export interface MealTimes {
  breakfast: string;
  lunch: string;
  dinner: string;
}

export interface CreateHouseholdPayload {
  name: string;
  pin: string;
  consent_given: boolean;
  meal_times: MealTimes;
  monthly_budget_bdt?: number | null;
}

export interface HouseholdAuthResponse {
  household_id: string;
  name: string;
  access_code: string;
  token: string;
  consent_given: boolean;
  meal_times: MealTimes;
  monthly_budget_bdt?: number | null;
}

export interface LoginHouseholdPayload {
  access_code: string;
  pin: string;
}

export interface HouseholdAlertRecord {
  id: string;
  kind: string;
  channel: string;
  sent_at: string;
  payload: Record<string, unknown>;
}

export interface NearExpiryStateItem {
  ingredient_key: string;
  name_bn: string;
  expiry_ratio: number | null;
}

export interface HouseholdStateResponse {
  household_id: string;
  name: string;
  access_code: string;
  consent_given: boolean;
  meal_times: MealTimes;
  monthly_budget_bdt?: number | null;
  for_date: string;
  members: MemberRecord[];
  present_member_count: number;
  guest_count: number;
  today_events: Array<{
    id?: string;
    kind: string;
    for_date?: string;
    payload?: Record<string, unknown>;
  }>;
  stock_item_count: number;
  near_expiry_items: NearExpiryStateItem[];
  recent_alerts: HouseholdAlertRecord[];
}

/* ---------- Member & Medicine Contracts ---------- */

export type MemberRole = "caregiver" | "patient" | "child" | "elder" | "other";
export type AgeGroup = "child_under_1" | "child_under_5" | "child" | "adult" | "elder";
export type DrugClass =
  | "ace_inhibitor"
  | "arb"
  | "k_sparing_diuretic"
  | "statin_cyp3a4"
  | "none_modelled";
export type MedTiming = "before_food" | "after_food" | "with_food" | "any" | "unknown";
export type MealSlot = "breakfast" | "lunch" | "dinner";

export interface MedicineRecord {
  id: string;
  name_as_written: string;
  generic_name?: string | null;
  drug_class: DrugClass | string;
  timing: MedTiming | string;
  meal_slots: MealSlot[];
  verified_by_caregiver: boolean;
  active: boolean;
  scheduled_doses?: number;
}

export interface LatestClinicianReview {
  id: string;
  doctor_name: string;
  clinician_reg_no?: string | null;
  clinician_note?: string | null;
  reviewed_at?: string | null;
  approved_diet_presets: string[];
}

export interface MemberRecord {
  id: string;
  household_id?: string;
  name: string;
  role: MemberRole | string;
  age_group: AgeGroup | string;
  conditions: string[];
  allergies: string[];
  diet_presets: string[];
  patient_token: string;
  notify_email?: string | null;
  created_at?: string;
  latest_clinician_review?: LatestClinicianReview | null;
  medicines: MedicineRecord[];
}

export interface DoseHistoryItem {
  id: string;
  medicine_id: string;
  due_at: string;
  window_end: string;
  status: string;
  confirmed_at: string | null;
}

export interface MemberDetailResponse extends MemberRecord {
  dose_history: DoseHistoryItem[];
}

export interface MemberCreatePayload {
  name: string;
  role: MemberRole;
  age_group: AgeGroup;
  conditions: string[];
  allergies: string[];
  diet_presets: string[];
  notify_email?: string | null;
}

export interface MemberUpdatePayload {
  name?: string;
  role?: MemberRole;
  age_group?: AgeGroup;
  conditions?: string[];
  allergies?: string[];
  diet_presets?: string[];
  notify_email?: string | null;
}

export interface MedicineCreatePayload {
  name_as_written: string;
  generic_name?: string | null;
  drug_class: DrugClass;
  timing: MedTiming;
  meal_slots: MealSlot[];
  verified_by_caregiver: boolean;
}

export interface MedicineUpdatePayload {
  drug_class?: DrugClass;
  timing?: MedTiming;
  meal_slots?: MealSlot[];
  verified_by_caregiver?: boolean;
  active?: boolean;
}

/* ---------- Prescription Contracts ---------- */

export interface DrugClassOption {
  value: DrugClass;
  label_bn: string;
  label_en: string;
}

export interface DrugClassesResponse {
  drug_classes: DrugClassOption[];
  note_bn: string;
  note_en: string;
}

export interface PrescriptionDraftMedicine {
  name_as_written: string;
  generic_guess?: string | null;
  timing: MedTiming;
  times_per_day?: number | null;
  confidence: number;
  suggested_drug_class?: DrugClass | null;
  drug_match_confidence?: number;
  low_confidence: boolean;
}

export interface PrescriptionDraftResponse {
  prescription_id: string;
  member_id: string;
  status: string;
  image_stored: boolean;
  confirmation_token: string;
  medicines: PrescriptionDraftMedicine[];
  diet_notes: string[];
  overall_confidence: number;
  extraction_failed: boolean;
  scope_note_bn: string;
  scope_note_en: string;
}

export interface PrescriptionConfirmRowPayload {
  name_as_written: string;
  generic_name?: string | null;
  drug_class: DrugClass;
  timing: MedTiming;
  meal_slots: MealSlot[];
  confirmed: boolean;
}

export interface PrescriptionConfirmResponse {
  prescription_id: string;
  status: string;
  confirmed_medicines: MedicineRecord[];
  scheduled_doses_count: number;
}

/* ---------- Events & Stock Contracts ---------- */

export type EventType =
  | "PURCHASED"
  | "COOKED"
  | "SPOILED"
  | "ADJUST"
  | "GUESTS"
  | "GUESTS_CANCELLED"
  | "MEMBER_AWAY";

export interface EventProposal {
  proposal_id: string;
  type: EventType;
  item_raw?: string | null;
  qty_phrase?: string | null;
  ingredient_key?: string | null;
  ingredient_name_bn?: string | null;
  ingredient_name_en?: string | null;
  qty_base?: number | null;
  unit_base?: string | null;
  confidence: number;
  needs_review: boolean;
  guest_count?: number | null;
  for_date?: string | null;
  guest_restrictions: string[];
  note?: string | null;
}

export interface EventParseResponse {
  raw_text: string;
  source: string;
  audio_stored: boolean;
  proposals: EventProposal[];
  parse_failed: boolean;
  confirmation_token: string;
}

export interface ConfirmedEventPayload {
  type: EventType;
  ingredient_key?: string | null;
  qty_base?: number | null;
  source?: "voice" | "text" | "ui" | "system";
  raw_text?: string | null;
  guest_count?: number | null;
  for_date?: string | null;
  guest_restrictions?: string[];
  member_id?: string | null;
}

export interface StockDeltaItem {
  ingredient_key: string;
  name_bn: string;
  name_en: string;
  before_qty: number;
  after_qty: number;
  unit: string;
}

export interface EventsConfirmResponse {
  written_count: number;
  written_event_ids: string[];
  stock_deltas: StockDeltaItem[];
  menu_stale: boolean;
}

export interface StockItem {
  ingredient_key: string;
  name_bn: string;
  name_en: string;
  category: string;
  base_unit: string;
  qty_base: number;
  raw_qty: number;
  clamped_negative: boolean;
  last_purchased_at: string | null;
  expiry_ratio: number | null;
  near_expiry: boolean;
  perishable_days: number;
}

export interface StockResponse {
  items: StockItem[];
}

export interface StockAdjustResponse {
  ingredient_key: string;
  previous_qty: number;
  new_qty: number;
  delta: number;
  unit: string;
}

export interface StockQuickAddResponse {
  ingredient_key: string;
  added_qty: number;
  previous_qty: number;
  new_qty: number;
  unit: string;
  last_purchased_at: string | null;
}

/* ---------- Daily Menu Contracts ---------- */

export interface MissingIngredientItem {
  ingredient_key: string;
  name_bn?: string;
  missing_qty: number;
  unit: string;
  est_cost_bdt?: number | null;
  is_estimated?: boolean;
}

export interface MenuTopDish {
  recipe_id: string;
  key: string;
  name_bn: string;
  name_en: string;
  category: string;
  servings_base: number;
  scaled_servings: number;
  status: "SAFE_DIRECT" | "SAFE_WITH_SPLIT" | string;
  split_for: string[];
  split_step_bn?: string | null;
  reasons: string[];
  score: number;
  components: Record<string, number>;
  missing_ingredients: MissingIngredientItem[];
  shortfall_cost_bdt: number;
  explanation_bn: string;
  explanation_en: string;
  split_instruction_bn?: string | null;
  split_instruction_en?: string | null;
  rule_ids: string[];
  used_template: boolean;
}

export interface ExcludedMemberDetail {
  member_name: string;
  status: "BLOCKED" | "UNVERIFIED" | string;
  reasons: string[];
  trace: string[];
}

export interface MenuExcludedDish {
  recipe_id: string;
  key: string;
  name_bn: string;
  name_en: string;
  reasons: string[];
  member_details: ExcludedMemberDetail[];
}

export interface MenuResponse {
  for_date: string;
  meal: MealSlot | string;
  people_count: number;
  present_member_names: string[];
  guest_count: number;
  total_candidates: number;
  top_3: MenuTopDish[];
  excluded: MenuExcludedDish[];
  validated: boolean;
  used_template: boolean;
  used_fallback: boolean;
}

export interface MenuCookedResponse {
  cooked_recipe_key: string;
  recipe_name_bn: string;
  servings: number;
  inventory_events_written: number;
}

/* ---------- Bazar Contracts ---------- */

export interface BazarItem {
  ingredient_key: string;
  name_bn: string;
  qty: number;
  unit: string;
  est_price_bdt: number;
  price_source: string;
  missing_price: boolean;
  is_estimated: boolean;
  label_bn: string;
  in_season: boolean;
  substitute_used: boolean;
  substituted_from?: string | null;
  dropped: boolean;
  flag?: string | null;
  category: string;
}

export interface BazarBuildResponse {
  bazar_list_id: string;
  status: string;
  month: string;
  budget_bdt: number;
  planned_recipes: Array<{ key: string; name_bn: string }>;
  items: BazarItem[];
  est_total_bdt: number;
  over_budget: boolean;
  price_label_bn: string;
  created_at?: string;
}

export interface BazarConfirmResponse {
  bazar_list_id: string;
  status: string;
  est_total_bdt: number;
  items: BazarItem[];
  price_label_bn: string;
}

export interface BazarPurchasedItemPayload {
  ingredient_key: string;
  qty_base: number;
  price_bdt?: number | null;
  per_qty?: number;
}

export interface BazarPurchasedResponse {
  events_written: number;
  prices_recorded: number;
}

/* ---------- Reminders & Patient Screen Contracts ---------- */

export interface PatientDueDose {
  dose_id: string;
  due_at: string;
  window_end: string;
  status: string;
  prompt_bn: string;
  prompt_en: string;
}

export interface PatientDueResponse {
  member_name: string;
  now: string;
  has_due_dose: boolean;
  due_doses: PatientDueDose[];
  upcoming_doses: PatientDueDose[];
  taken_today_count: number;
}

export interface DoseTakenResponse {
  dose_id: string;
  status: string;
  confirmed_at: string | null;
}

export interface CaregiverDoseRow {
  dose_id: string;
  medicine_id: string;
  medicine_name: string;
  timing: string;
  due_at: string;
  window_end: string;
  status: string;
  confirmed_at: string | null;
}

export interface CaregiverPatientDoses {
  member_id: string;
  name: string;
  role: string;
  patient_token: string;
  doses: CaregiverDoseRow[];
}

export interface CaregiverDosesDashboardResponse {
  for_date: string;
  summary: {
    taken: number;
    taken_late: number;
    pending: number;
    missed: number;
    escalated: number;
  };
  patients: CaregiverPatientDoses[];
  alerts: HouseholdAlertRecord[];
}

/* ---------- Engine Explorer & Eval Contracts ---------- */

export interface EngineRecipeSummary {
  id: string;
  key: string;
  name_bn: string;
  name_en: string;
  category: string;
  split_step_bn?: string | null;
  split_removes: string[];
}

export interface EngineCatalogResponse {
  recipes: EngineRecipeSummary[];
  members: MemberRecord[];
  presets: string[];
  allergens: string[];
  drug_classes: DrugClass[];
  age_groups: AgeGroup[];
}

export interface EngineCheckIngredient {
  key: string;
  name_bn: string;
  name_en: string;
  potassium_level: string | null;
  purine_level: string | null;
  sodium_level: string | null;
  gi_level: string | null;
  allergen_tags: string[];
}

export interface EngineCheckResponse {
  member_name: string;
  recipe_key: string;
  recipe_name_bn: string;
  recipe_name_en: string;
  status: "SAFE_DIRECT" | "SAFE_WITH_SPLIT" | "BLOCKED" | "UNVERIFIED" | string;
  reasons: string[];
  trace: string[];
  split_step_bn?: string | null;
  split_ingredients: string[];
  ingredients: EngineCheckIngredient[];
}

export interface EvalResultsResponse {
  status: "available" | "not_run_yet";
  results: Record<string, unknown> | null;
  markdown: string;
  note_bn?: string;
  note_en?: string;
}

/* ---------- Clinician Review & Fee History Contracts ---------- */

export type ClinicianContactMode = "email_invite" | "family_direct";
export type ClinicianPaymentStatus = "unpaid" | "paid" | "waived";
export type ClinicianPaymentMethod = "bkash" | "nagad" | "card" | "cash_clinic";
export type ClinicianReviewStatus = "pending" | "approved" | "changes_requested";

export interface ClinicianSnapshotMedicine {
  name_as_written: string;
  generic_name?: string | null;
  drug_class: string;
  timing: string;
  meal_slots: string[];
}

export interface ClinicianReviewSnapshot {
  member_name: string;
  role: string;
  age_group: string;
  conditions: string[];
  allergies: string[];
  diet_presets: string[];
  medicines: ClinicianSnapshotMedicine[];
  adherence_30d: {
    taken: number;
    taken_late: number;
    missed: number;
    escalated: number;
    pending: number;
    total: number;
    adherence_pct: number | null;
  };
  recent_meals: Array<{
    for_date: string;
    meal: string;
    dish_bn: string;
    dish_en: string;
    status: string;
  }>;
}

export interface ClinicianReviewRecord {
  id: string;
  household_id: string;
  member_id: string;
  member_name: string;
  review_token: string;
  review_url_path: string;
  doctor_name: string;
  doctor_email?: string | null;
  contact_mode: ClinicianContactMode;
  request_note?: string | null;
  clinical_snapshot: ClinicianReviewSnapshot;
  fee_bdt: number;
  payment_status: ClinicianPaymentStatus;
  payment_method?: string | null;
  payment_ref?: string | null;
  paid_at?: string | null;
  email_status: "sent" | "link_ready" | "not_requested" | "failed" | string;
  status: ClinicianReviewStatus;
  clinician_reg_no?: string | null;
  clinician_note?: string | null;
  approved_diet_presets: string[];
  apply_presets_on_approve: boolean;
  created_at: string;
  reviewed_at?: string | null;
}

export interface ClinicianPaymentSummary {
  total_paid_bdt: number;
  total_unpaid_bdt: number;
  paid_count: number;
  unpaid_count: number;
  approved_count: number;
  pending_count: number;
  changes_requested_count: number;
}

export interface ClinicianReviewsListResponse {
  reviews: ClinicianReviewRecord[];
  payment_summary: ClinicianPaymentSummary;
}

export interface ClinicianPortalResponse extends ClinicianReviewRecord {
  household_name: string;
  member_current_diet_presets: string[];
  available_presets: string[];
}

/* ---------- API Client ---------- */

export const harborApi = {
  healthz: (locale: Locale = "bn") =>
    apiFetch<HealthResponse>("/healthz", { locale }),

  createHousehold: (payload: CreateHouseholdPayload, locale: Locale = "bn") =>
    apiFetch<HouseholdAuthResponse>("/households", {
      method: "POST",
      body: payload,
      locale,
    }),

  loginHousehold: (payload: LoginHouseholdPayload, locale: Locale = "bn") =>
    apiFetch<HouseholdAuthResponse>("/households/login", {
      method: "POST",
      body: payload,
      locale,
    }),

  seedDemoHousehold: (locale: Locale = "bn") =>
    apiFetch<HouseholdAuthResponse>("/households/demo", {
      method: "POST",
      locale,
    }),

  getHouseholdState: (
    householdId: string,
    token: string,
    locale: Locale = "bn",
    forDate?: string,
  ) =>
    apiFetch<HouseholdStateResponse>(
      `/households/${householdId}/state${forDate ? `?for_date=${encodeURIComponent(forDate)}` : ""}`,
      { token, locale },
    ),

  updateHouseholdSettings: (
    householdId: string,
    payload: Partial<CreateHouseholdPayload>,
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<Record<string, unknown>>(`/households/${householdId}/settings`, {
      method: "PATCH",
      body: payload,
      token,
      locale,
    }),

  listMembers: (token: string, locale: Locale = "bn") =>
    apiFetch<{ members: MemberRecord[] }>("/members", { token, locale }),

  getMember: (memberId: string, token: string, locale: Locale = "bn") =>
    apiFetch<MemberDetailResponse>(`/members/${memberId}`, { token, locale }),

  createMember: (payload: MemberCreatePayload, token: string, locale: Locale = "bn") =>
    apiFetch<MemberRecord>("/members", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  updateMember: (
    memberId: string,
    payload: MemberUpdatePayload,
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<MemberRecord>(`/members/${memberId}`, {
      method: "PATCH",
      body: payload,
      token,
      locale,
    }),

  deleteMember: (memberId: string, token: string, locale: Locale = "bn") =>
    apiFetch<{ deleted: boolean; member_id: string }>(`/members/${memberId}`, {
      method: "DELETE",
      token,
      locale,
    }),

  addMedicine: (
    memberId: string,
    payload: MedicineCreatePayload,
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<MedicineRecord>(`/members/${memberId}/medicines`, {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  updateMedicine: (
    memberId: string,
    medicineId: string,
    payload: MedicineUpdatePayload,
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<MedicineRecord>(`/members/${memberId}/medicines/${medicineId}`, {
      method: "PATCH",
      body: payload,
      token,
      locale,
    }),

  deleteMedicine: (
    memberId: string,
    medicineId: string,
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<{ deleted: boolean; medicine_id: string }>(
      `/members/${memberId}/medicines/${medicineId}`,
      { method: "DELETE", token, locale },
    ),

  getDrugClasses: (locale: Locale = "bn") =>
    apiFetch<DrugClassesResponse>("/drug-classes", { locale }),

  uploadPrescription: (
    memberId: string,
    file: File,
    token: string,
    locale: Locale = "bn",
  ) => {
    const fd = new FormData();
    fd.append("file", file);
    return apiFetch<PrescriptionDraftResponse>(`/members/${memberId}/prescription`, {
      method: "POST",
      body: fd,
      token,
      locale,
    });
  },

  confirmPrescription: (
    prescriptionId: string,
    rows: PrescriptionConfirmRowPayload[],
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<PrescriptionConfirmResponse>(`/prescriptions/${prescriptionId}/confirm`, {
      method: "POST",
      body: { rows },
      token,
      locale,
    }),

  parseEventsText: (text: string, token: string, locale: Locale = "bn") =>
    apiFetch<EventParseResponse>("/events/parse", {
      method: "POST",
      body: { text },
      token,
      locale,
    }),

  parseEventsAudio: (audioBlob: Blob, token: string, locale: Locale = "bn") => {
    const fd = new FormData();
    fd.append("audio", audioBlob, "voice.webm");
    return apiFetch<EventParseResponse>("/events/parse", {
      method: "POST",
      body: fd,
      token,
      locale,
    });
  },

  confirmEvents: (
    confirmationToken: string,
    events: ConfirmedEventPayload[],
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<EventsConfirmResponse>("/events/confirm", {
      method: "POST",
      body: { confirmation_token: confirmationToken, events },
      token,
      locale,
    }),

  getStock: (token: string, locale: Locale = "bn") =>
    apiFetch<StockResponse>("/stock", { token, locale }),

  adjustStock: (
    ingredientKey: string,
    targetQtyBase: number,
    note: string | undefined,
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<StockAdjustResponse>("/stock/adjust", {
      method: "POST",
      body: {
        ingredient_key: ingredientKey,
        target_qty_base: targetQtyBase,
        note,
      },
      token,
      locale,
    }),

  quickAddStock: (
    payload: {
      ingredient_key: string;
      qty_base: number;
      price_bdt?: number | null;
      note?: string;
    },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<StockQuickAddResponse>("/stock/quick-add", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  suggestMenu: (
    payload: { for_date: string; meal: MealSlot; use_agent: boolean },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<MenuResponse>("/menu/suggest", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  reviewMenu: (
    payload: {
      for_date: string;
      meal: MealSlot;
      guest_count: number;
      guest_restrictions: string[];
      away_member_ids: string[];
      use_agent?: boolean;
    },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<MenuResponse>("/menu/review", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  markMenuCooked: (
    payload: { recipe_id: string; servings: number; for_date: string; meal?: MealSlot },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<MenuCookedResponse>("/menu/cooked", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  buildBazar: (
    payload: { month: string; budget_bdt: number },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<BazarBuildResponse>("/bazar/build", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  confirmBazar: (
    payload: { bazar_list_id: string; items: BazarItem[] },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<BazarConfirmResponse>("/bazar/confirm", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  logBazarPurchased: (
    payload: { bazar_list_id?: string | null; items: BazarPurchasedItemPayload[] },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<BazarPurchasedResponse>("/bazar/purchased", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  getLatestBazar: (token: string, locale: Locale = "bn") =>
    apiFetch<{ bazar_list: BazarBuildResponse | null }>("/bazar/latest", {
      token,
      locale,
    }),

  getPatientDueReminders: (patientToken: string, locale: Locale = "bn") =>
    apiFetch<PatientDueResponse>(
      `/reminders/due?token=${encodeURIComponent(patientToken)}`,
      { locale },
    ),

  markPatientDoseTaken: (
    doseId: string,
    patientToken: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<DoseTakenResponse>(
      `/reminders/${doseId}/taken?token=${encodeURIComponent(patientToken)}`,
      { method: "POST", locale },
    ),

  getCaregiverDosesDashboard: (
    token: string,
    locale: Locale = "bn",
    forDate?: string,
  ) =>
    apiFetch<CaregiverDosesDashboardResponse>(
      `/dashboard/doses${forDate ? `?for_date=${encodeURIComponent(forDate)}` : ""}`,
      { token, locale },
    ),

  getVapidPublicKey: (locale: Locale = "bn") =>
    apiFetch<{ public_key: string; configured: boolean }>("/push/vapid-public-key", {
      locale,
    }),

  subscribePush: (
    payload: { member_id?: string | null; endpoint: string; p256dh: string; auth: string },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<{ subscribed: boolean }>("/push/subscribe", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  subscribePatientPush: (
    patientToken: string,
    payload: { endpoint: string; p256dh: string; auth: string },
    locale: Locale = "bn",
  ) =>
    apiFetch<{ subscribed: boolean }>(
      `/push/subscribe-patient?token=${encodeURIComponent(patientToken)}`,
      {
        method: "POST",
        body: payload,
        locale,
      },
    ),

  getEngineCatalog: (token?: string | null, locale: Locale = "bn") =>
    apiFetch<EngineCatalogResponse>("/engine/catalog", {
      token: token || undefined,
      locale,
    }),

  checkEngineRuleTrace: (
    payload: {
      member_id?: string | null;
      recipe_key: string;
      custom_member?: Record<string, unknown> | null;
    },
    token?: string | null,
    locale: Locale = "bn",
  ) =>
    apiFetch<EngineCheckResponse>("/engine/check", {
      method: "POST",
      body: payload,
      token: token || undefined,
      locale,
    }),

  getEvalResults: (locale: Locale = "bn") =>
    apiFetch<EvalResultsResponse>("/eval/results", { locale }),

  listClinicianReviews: (token: string, locale: Locale = "bn") =>
    apiFetch<ClinicianReviewsListResponse>("/clinician/reviews", { token, locale }),

  createClinicianReview: (
    payload: {
      member_id: string;
      doctor_name: string;
      doctor_email?: string | null;
      contact_mode: ClinicianContactMode;
      fee_bdt: number;
      request_note?: string | null;
      frontend_origin?: string | null;
    },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<ClinicianReviewRecord>("/clinician/reviews", {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  payClinicianReview: (
    reviewId: string,
    payload: {
      payment_method: ClinicianPaymentMethod;
      payment_ref?: string | null;
    },
    token: string,
    locale: Locale = "bn",
  ) =>
    apiFetch<ClinicianReviewRecord>(`/clinician/reviews/${reviewId}/pay`, {
      method: "POST",
      body: payload,
      token,
      locale,
    }),

  getClinicianPortal: (reviewToken: string, locale: Locale = "bn") =>
    apiFetch<ClinicianPortalResponse>(`/clinician/portal/${encodeURIComponent(reviewToken)}`, {
      locale,
    }),

  submitClinicianDecision: (
    reviewToken: string,
    payload: {
      decision: "approved" | "changes_requested";
      clinician_reg_no?: string | null;
      clinician_note: string;
      approved_diet_presets: string[];
      apply_presets_to_member: boolean;
    },
    locale: Locale = "bn",
  ) =>
    apiFetch<ClinicianPortalResponse>(
      `/clinician/portal/${encodeURIComponent(reviewToken)}/decision`,
      {
        method: "POST",
        body: payload,
        locale,
      },
    ),
};
