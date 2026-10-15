export type Readiness = { request_id: string; data: { status: "ready"; phase: 2 } };

export class ApiError extends Error {
  constructor(message: string, public readonly requestId?: string, public readonly status?: number) { super(message); }
}

export async function getReadiness(signal: AbortSignal): Promise<Readiness> {
  const response = await fetch("/api/v1/health/ready", { cache: "no-store", signal });
  const body: unknown = await response.json();
  if (!response.ok) {
    throw new ApiError("The service is unavailable. Check local setup, then try again.",
      response.headers.get("X-Request-ID") ?? undefined);
  }
  if (typeof body !== "object" || body === null || !("request_id" in body) ||
      typeof body.request_id !== "string" || !("data" in body) ||
      typeof body.data !== "object" || body.data === null ||
      !("status" in body.data) || body.data.status !== "ready" ||
      !("phase" in body.data) || body.data.phase !== 2) {
    throw new ApiError("The service returned an unexpected response.");
  }
  return { request_id: body.request_id, data: { status: "ready", phase: 2 } };
}

let csrfToken: string | null = null;
async function ensureCsrf(): Promise<string> {
  if (!csrfToken) {
    const tokenResponse = await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
    if (!tokenResponse.ok) throw new ApiError("Could not start a secure session.");
    const tokenBody = await tokenResponse.json();
    csrfToken = tokenBody.data.csrf_token;
  }
  return csrfToken!;
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method ?? "GET";
  if (method !== "GET") await ensureCsrf();
  const headers = new Headers(options.headers);
  if (method !== "GET" && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`/api/v1${path}`, { ...options, headers,
    credentials: "same-origin", cache: "no-store" });
  if (response.status === 401) {
    csrfToken = null;
    window.dispatchEvent(new Event("session-expired"));
  }
  const body = await response.json();
  if (!response.ok) throw new ApiError(body.error?.message ?? "Request failed.", body.request_id, response.status);
  return body.data as T;
}

export async function uploadDatasets<T>(files: File[], uploaded: () => void): Promise<T> {
  const token = await ensureCsrf();
  return new Promise<T>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/v1/datasets");
    request.withCredentials = true;
    request.setRequestHeader("X-CSRF-Token", token);
    request.upload.addEventListener("load", uploaded);
    request.addEventListener("load", () => {
      try {
        const body = JSON.parse(request.responseText);
        if (request.status === 401) {
          csrfToken = null; window.dispatchEvent(new Event("session-expired"));
        }
        if (request.status < 200 || request.status >= 300) {
          reject(new ApiError(body.error?.message ?? "Upload failed.", body.request_id));
        } else resolve(body.data as T);
      } catch { reject(new ApiError("Upload returned an invalid response.")); }
    });
    request.addEventListener("error", () => reject(new ApiError("Upload connection failed.")));
    const form = new FormData(); files.forEach(file => form.append("files", file));
    request.send(form);
  });
}

export function clearPrivateState() { csrfToken = null; sessionStorage.removeItem("selected-datasets"); }

export async function downloadReport(title: string, analysisIds: string[]) {
  const token = await ensureCsrf();
  const response = await fetch("/api/v1/reports/export", { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
    body: JSON.stringify({ title, analysis_ids: analysisIds }) });
  if (!response.ok) {
    if (response.status === 401) { csrfToken = null; window.dispatchEvent(new Event("session-expired")); }
    throw new ApiError("Report unavailable. Check selections and source availability, then try again.");
  }
  const filename = response.headers.get("Content-Disposition")?.match(/filename="([a-zA-Z0-9_-]+\.html)"/)?.[1];
  if (!filename || !response.headers.get("Content-Type")?.startsWith("text/html")) throw new ApiError("Invalid report response.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
