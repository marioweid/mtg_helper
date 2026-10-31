import { auth } from "@/auth";
import { localIdentityEnabled } from "@/lib/local-identity";

interface AppUser {
  id?: string;
  name?: string | null;
  email?: string | null;
}

/** Resolve backend credentials without pretending a local account has a Google token. */
export async function getBackendHeaders(): Promise<Headers | null> {
  if (localIdentityEnabled()) return new Headers();
  const session = await auth();
  if (!session?.idToken || session.error === "RefreshFailed") return null;
  return new Headers({ authorization: `Bearer ${session.idToken}` });
}

/** Read the same fixed account the backend authorizes, or the existing Google session. */
export async function getAppUser(): Promise<AppUser | null> {
  if (!localIdentityEnabled()) {
    const session = await auth();
    return session?.error === "RefreshFailed" ? null : (session?.user ?? null);
  }
  const response = await fetch(`${process.env["BACKEND_ORIGIN"]}/api/v1/me`, { cache: "no-store" });
  if (!response.ok)
    throw new Error(`Local developer account is unavailable (HTTP ${response.status}).`);
  const result = (await response.json()) as {
    data?: { id?: string; display_name?: string; email?: string };
  };
  if (!result.data?.id || !result.data.email) {
    throw new Error("Local developer account is missing. Check LOCAL_DEV_ACCOUNT_ID.");
  }
  return { id: result.data.id, name: result.data.display_name ?? null, email: result.data.email };
}
