import { PageHeader } from "@/components/page-header";

export default function PreferencesPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Preferences" />
      <section className="rounded-xl border border-white/10 bg-white/5 p-6 text-gray-400">
        <p>Nothing in here yet.</p>
        <p className="mt-2">Profile settings may come in the future.</p>
      </section>
    </div>
  );
}
