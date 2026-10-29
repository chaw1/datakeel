export class ApiError extends Error {
  constructor(
    public readonly status: number,
    detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}
async function request<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const response = await fetch(path, { ...init, headers });
  await requireSuccess(response);
  return response.json() as Promise<T>;
}
export function get<T>(path: string, headers?: HeadersInit): Promise<T> {
  return request(path, { method: "GET", ...(headers ? { headers } : {}) });
}
export function post<T>(path: string, body: unknown): Promise<T> {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function requireSuccess(response: Response): Promise<void> {
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : response.statusText;
    throw new ApiError(response.status, `${String(response.status)} ${detail}`);
  }
}
