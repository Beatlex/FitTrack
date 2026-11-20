export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly path: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function responseMessage(body: string, path: string, status: number): string {
  let detail: unknown;
  try {
    detail = (JSON.parse(body) as { detail?: unknown }).detail;
  } catch {
    detail = undefined;
  }

  const message = Array.isArray(detail)
    ? detail.map((item: { msg?: string }) => item.msg ?? "Ungültige Eingabe").join("; ")
    : typeof detail === "string"
      ? detail
      : body.trim().slice(0, 240);

  return message
    ? `HTTP ${status} bei ${path}: ${message}`
    : `HTTP ${status} bei ${path}: Der Server hat keine Fehlerbeschreibung geliefert.`;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(responseMessage(body, path, response.status), response.status, path);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
