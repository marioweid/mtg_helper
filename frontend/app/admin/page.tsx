import { redirect } from "next/navigation";
import { AdminPanel } from "@/components/admin-panel";
import { getAdminEmail } from "@/lib/admin";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const email = await getAdminEmail();
  if (!email) redirect("/decks");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Admin</h1>
        <p className="text-sm text-gray-400">
          Signed in as <span className="font-mono">{email}</span>. Card pipeline
          jobs run server-side and may take a minute.
        </p>
      </header>
      <AdminPanel />
    </div>
  );
}
