/** Request helpers shared by the webhook and the daily check. */

export function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function secretsMatch(expected: string, got: string | null): boolean {
  if (got === null) {
    return false;
  }
  const left = new TextEncoder().encode(expected);
  const right = new TextEncoder().encode(got);
  if (left.length !== right.length) {
    return false;
  }
  let diff = 0;
  for (let index = 0; index < left.length; index++) {
    diff |= left[index] ^ right[index];
  }
  return diff === 0;
}

export function allowedChatIds(): Set<number> | null {
  const raw = Deno.env.get("TELEGRAM_ALLOWED_CHAT_IDS");
  if (raw === undefined || raw.trim() === "") {
    return null;
  }
  const ids = new Set<number>();
  for (const part of raw.split(",")) {
    const piece = part.trim();
    if (!piece) {
      continue;
    }
    if (!/^-?\d+$/.test(piece)) {
      throw new Error(
        "TELEGRAM_ALLOWED_CHAT_IDS must be a comma-separated list of integers",
      );
    }
    ids.add(Number(piece));
  }
  return ids;
}

export function checkTimezone(): string {
  const raw = Deno.env.get("CHECK_TIMEZONE");
  if (raw === undefined || raw.trim() === "") {
    return "UTC";
  }
  return raw.trim();
}

export function requiredSecret(name: string): string {
  const value = Deno.env.get(name)?.trim() ?? "";
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}
