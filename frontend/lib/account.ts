"use client";

import { apiClient } from "@/lib/api";
import type { AccountResponse } from "@/lib/types";

let cached: AccountResponse | null = null;
let inflight: Promise<AccountResponse> | null = null;

export async function getCurrentAccount(): Promise<AccountResponse> {
  if (cached) return cached;
  if (inflight) return inflight;
  inflight = apiClient.getMe().then((acc) => {
    cached = acc;
    inflight = null;
    return acc;
  });
  return inflight;
}

export async function getCurrentAccountId(): Promise<string> {
  const acc = await getCurrentAccount();
  return acc.id;
}
