import { getAppUser } from "@/lib/app-identity";

function adminEmails(): Set<string> {
  const raw = process.env["ADMIN_EMAILS"] ?? "";
  return new Set(
    raw
      .split(",")
      .map((e) => e.trim().toLowerCase())
      .filter(Boolean),
  );
}

export function isAdminEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  return adminEmails().has(email.toLowerCase());
}

export async function getAdminEmail(): Promise<string | null> {
  const user = await getAppUser();
  const email = user?.email ?? null;
  return isAdminEmail(email) ? email : null;
}
