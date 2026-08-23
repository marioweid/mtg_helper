export const INITIAL_ASSISTANT_PROMPT = "";

export const ASSISTANT_STARTER_PROMPTS = [
  "Find the weakest cards in this deck.",
  "Suggest upgrades for my main theme.",
  "What should I replace this card with?",
  "Check my mana, draw, and interaction balance.",
  "Convert this deck into an aristocrats deck — what should I cut and add?",
  "Make this deck bracket 3 legal — which Game Changers should go?",
] as const;

export function AssistantStarterPrompts({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="max-w-2xl rounded-2xl border border-white/10 bg-white/5 p-5">
      <h2 className="font-semibold text-white">Ask the Assistant</h2>
      <p className="mt-2 text-sm text-gray-400">
        Choose an example to edit, or write your own request.
      </p>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {ASSISTANT_STARTER_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onSelect(prompt)}
            className="rounded-xl border border-white/10 bg-black/20 px-3 py-3 text-left text-sm text-gray-200 transition hover:border-indigo-400/40 hover:bg-indigo-950/20"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
