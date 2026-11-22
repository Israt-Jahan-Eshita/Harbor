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

export interface HealthResponse {
  status: string;
  db: string;
}

export interface CreateHouseholdPayload {
  name: string;
  pin: string;
  consent_given: boolean;
  meal_times: { breakfast: string; lunch: string; dinner: string };
  monthly_budget_bdt?: number | null;
}

export interface HouseholdAuthResponse {
  household_id: string;
  name: string;
  access_code: string;
  token: string;
  consent_given: boolean;
  meal_times: { breakfast: string; lunch: string; dinner: string };
  monthly_budget_bdt?: number | null;
}

export interface LoginHouseholdPayload {
  access_code: string;
  pin: string;
}

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
  getHouseholdState: (householdId: string, token: string, locale: Locale = "bn") =>
    apiFetch<Record<string, unknown>>(`/households/${householdId}/state`, {
      token,
      locale,
    }),
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
  seedDemoHousehold: (locale: Locale = "bn") =>
    apiFetch<HouseholdAuthResponse>("/households/demo", {
      method: "POST",
      locale,
    }),
};

