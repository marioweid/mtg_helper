import type { ReactNode } from "react";

interface Props {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

/**
 * Shared page header used across the top-level pages (decks, collections,
 * preferences). Title on the left, optional subtitle below it, and an
 * action slot on the right that flexes onto a new line on narrow viewports.
 */
export function PageHeader({ title, subtitle, actions }: Props) {
  return (
    <header className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold leading-tight text-white sm:text-3xl">{title}</h1>
        {subtitle ? <p className="text-sm text-gray-400">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
