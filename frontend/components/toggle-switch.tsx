"use client";

interface Props {
  enabled: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function ToggleSwitch({ enabled, onToggle, disabled = false }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={onToggle}
      disabled={disabled}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full
        border-2 border-transparent transition-colors duration-200 focus:outline-none
        focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-gray-900
        disabled:cursor-not-allowed disabled:opacity-50
        ${enabled ? "bg-indigo-600" : "bg-gray-600"}`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition
          duration-200 ${enabled ? "translate-x-5" : "translate-x-0"}`}
      />
    </button>
  );
}
