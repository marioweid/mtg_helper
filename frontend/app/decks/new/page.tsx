import Link from "next/link";

import { PageHeader } from "@/components/page-header";

export const metadata = {
  title: "New Deck",
};

const OPTIONS: { href: string; title: string; subtitle: string; description: string }[] = [
  {
    href: "/decks/new/keywords",
    title: "Pick keywords",
    subtitle: "Fastest path",
    description:
      "Pick a commander, then chip-select archetype keywords (voltron, aristocrats, squirrel tribal…) and tribal subtypes. Suggestions are tag-driven from there.",
  },
  {
    href: "/decks/new/agent",
    title: "Chat with the agent",
    subtitle: "Best for fuzzy ideas",
    description:
      "Describe what you want; the agent asks 1–3 short questions, then converges on the same archetype keywords for you. You can fine-tune the chips before creating.",
  },
  {
    href: "/decks/import",
    title: "Import a deck list",
    subtitle: "Already have a list",
    description:
      "Paste a Moxfield/Archidekt list or URL. After import you'll set archetype keywords from the cards we detected so further suggestions stay on-theme.",
  },
];

export default function NewDeckChooser() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Start a new deck"
        subtitle="Three paths. Pick whichever fits your mood — they all converge on the same keyword-driven suggestion engine."
      />

      <p className="mb-6 text-xs text-gray-500">
        New here? Try the{" "}
        <Link
          href="/onboarding"
          className="text-indigo-400 underline transition-colors hover:text-indigo-300"
        >
          one-click quickstart
        </Link>{" "}
        instead — it builds a sample deck for you.
      </p>

      <div className="grid gap-4 sm:grid-cols-1">
        {OPTIONS.map((opt) => (
          <Link
            key={opt.href}
            href={opt.href}
            className="group rounded-xl border border-white/10 bg-white/5 p-6 transition-all hover:-translate-y-0.5 hover:border-indigo-500/70 hover:bg-indigo-900/20 hover:shadow-lg hover:shadow-indigo-900/30"
          >
            <div className="mb-1 flex items-baseline justify-between">
              <h2 className="text-lg font-semibold text-white">{opt.title}</h2>
              <span className="text-xs uppercase tracking-wide text-indigo-400">
                {opt.subtitle}
              </span>
            </div>
            <p className="text-sm text-gray-400">{opt.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
