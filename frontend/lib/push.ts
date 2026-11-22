import { harborApi, Locale } from "@/lib/api";

export type PushSubscribeResult =
  | { ok: true; reason: "subscribed" }
  | { ok: false; reason: "unsupported" | "denied" | "not_configured" | "error" };

function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const buffer = new ArrayBuffer(rawData.length);
  const outputArray = new Uint8Array(buffer);
  for (let i = 0; i < rawData.length; i += 1) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

function arrayBufferToBase64Url(buf: ArrayBuffer | null): string {
  if (!buf) return "";
  const bytes = new Uint8Array(buf);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) {
    return null;
  }
  try {
    return await navigator.serviceWorker.register("/sw.js");
  } catch {
    return null;
  }
}

async function createBrowserPushSubscription(
  locale: Locale,
): Promise<
  | { ok: true; endpoint: string; p256dh: string; auth: string }
  | { ok: false; reason: "unsupported" | "denied" | "not_configured" | "error" }
> {
  if (
    typeof window === "undefined" ||
    !("serviceWorker" in navigator) ||
    !("PushManager" in window) ||
    typeof Notification === "undefined"
  ) {
    return { ok: false, reason: "unsupported" };
  }

  let vapidPublicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY || "";
  if (!vapidPublicKey) {
    try {
      const cfg = await harborApi.getVapidPublicKey(locale);
      if (cfg.configured && cfg.public_key) {
        vapidPublicKey = cfg.public_key;
      }
    } catch {
      /* handled below */
    }
  }
  if (!vapidPublicKey) {
    return { ok: false, reason: "not_configured" };
  }

  const permission =
    Notification.permission === "granted"
      ? "granted"
      : await Notification.requestPermission();
  if (permission !== "granted") {
    return { ok: false, reason: "denied" };
  }

  const reg = (await registerServiceWorker()) || (await navigator.serviceWorker.ready);
  if (!reg?.pushManager) {
    return { ok: false, reason: "unsupported" };
  }

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
    });
  }

  const p256dh = arrayBufferToBase64Url(sub.getKey("p256dh"));
  const auth = arrayBufferToBase64Url(sub.getKey("auth"));
  if (!sub.endpoint || !p256dh || !auth) {
    return { ok: false, reason: "error" };
  }
  return { ok: true, endpoint: sub.endpoint, p256dh, auth };
}

export async function subscribeCaregiverPush(
  token: string,
  locale: Locale,
): Promise<PushSubscribeResult> {
  try {
    const sub = await createBrowserPushSubscription(locale);
    if (!sub.ok) return sub;
    await harborApi.subscribePush(
      { endpoint: sub.endpoint, p256dh: sub.p256dh, auth: sub.auth },
      token,
      locale,
    );
    return { ok: true, reason: "subscribed" };
  } catch {
    return { ok: false, reason: "error" };
  }
}

export async function subscribePatientPush(
  patientToken: string,
  locale: Locale,
): Promise<PushSubscribeResult> {
  try {
    const sub = await createBrowserPushSubscription(locale);
    if (!sub.ok) return sub;
    await harborApi.subscribePatientPush(
      patientToken,
      { endpoint: sub.endpoint, p256dh: sub.p256dh, auth: sub.auth },
      locale,
    );
    return { ok: true, reason: "subscribed" };
  } catch {
    return { ok: false, reason: "error" };
  }
}

