type ApiOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  token?: string;
  body?: unknown;
  form?: Record<string, string>;
  multipart?: FormData;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers();
  let body: BodyInit | undefined;

  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  if (options.multipart) {
    body = options.multipart;
  } else if (options.form) {
    const form = new URLSearchParams();
    Object.entries(options.form).forEach(([key, value]) => form.set(key, value));
    body = form;
    headers.set("Content-Type", "application/x-www-form-urlencoded");
  } else if (options.body !== undefined) {
    body = JSON.stringify(options.body);
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail ?? "API request failed.");
  }
  return payload as T;
}
