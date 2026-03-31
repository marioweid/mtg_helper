import { STAGES, STAGE_LABELS } from "@/lib/constants";

interface Props {
  currentStage: string;
}

export function StageProgress({ currentStage }: Props) {
  const currentIndex = STAGES.indexOf(currentStage as (typeof STAGES)[number]);

  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-1">
      {STAGES.map((stage, i) => {
        const isDone = i < currentIndex;
        const isCurrent = i === currentIndex;
        return (
          <div key={stage} className="flex items-center gap-1">
            {i > 0 && (
              <div
                className={`h-px w-4 flex-shrink-0 ${isDone ? "bg-indigo-500" : "bg-white/10"}`}
              />
            )}
            <div
              className={`flex-shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                isCurrent
                  ? "bg-indigo-600 text-white"
                  : isDone
                    ? "bg-indigo-900/60 text-indigo-300"
                    : "bg-white/5 text-gray-500"
              }`}
            >
              {STAGE_LABELS[stage] ?? stage}
            </div>
          </div>
        );
      })}
    </div>
  );
}
