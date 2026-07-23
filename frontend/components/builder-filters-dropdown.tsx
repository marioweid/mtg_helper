"use client";

import { useEffect, useRef, useState } from "react";

import type { CollectionResponse } from "@/lib/types";

const PRIMARY_TYPE_OPTIONS = [
  "Creature",
  "Instant",
  "Sorcery",
  "Artifact",
  "Enchantment",
  "Planeswalker",
  "Land",
  "Battle",
] as const;

const SUBTYPE_OPTIONS = [
  "Equipment",
  "Aura",
  "Vehicle",
  "Saga",
  "Background",
  "Class",
  "Food",
  "Treasure",
  "Clue",
] as const;

interface Props {
  collections: CollectionResponse[];
  selectedCollectionIds: string[];
  minPriceCents: number | null;
  maxPriceCents: number | null;
  minPriceDraft: string;
  maxPriceDraft: string;
  cardTypes: string[];
  subtypes: string[];
  onToggleOwnedOnly: () => void;
  onToggleCollection: (id: string) => void;
  onSelectAllCollections: () => void;
  onClearCollections: () => void;
  onMinPriceDraftChange: (value: string) => void;
  onMaxPriceDraftChange: (value: string) => void;
  onApplyPrice: () => void;
  onClearPrice: () => void;
  onCardTypesChange: (types: string[]) => void;
  onSubtypesChange: (subtypes: string[]) => void;
  onClearAll: () => void;
}

export function BuilderFiltersDropdown(props: Props) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const ownedActive = props.selectedCollectionIds.length > 0;
  const priceActive = props.minPriceCents != null || props.maxPriceCents != null;
  const activeCount =
    (ownedActive ? 1 : 0) +
    (priceActive ? 1 : 0) +
    props.cardTypes.length +
    props.subtypes.length;
  const hasDraft = Boolean(props.minPriceDraft.trim() || props.maxPriceDraft.trim());

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div ref={wrapperRef} className="relative mb-4">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="builder-filters-dropdown"
        onClick={() => setOpen((current) => !current)}
        className={
          "flex min-h-11 items-center gap-2 rounded-lg border border-white/15 bg-white/5 " +
          "px-4 py-2 text-sm font-medium text-white hover:bg-white/10"
        }
      >
        Filters
        {activeCount > 0 && (
          <span className="rounded-full bg-indigo-600/40 px-2 py-0.5 text-xs text-indigo-100">
            {activeCount}
          </span>
        )}
        <span className="text-xs text-gray-400" aria-hidden="true">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <FiltersMenu
          filters={props}
          activeCount={activeCount}
          hasDraft={hasDraft}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}

function FiltersMenu({
  filters,
  activeCount,
  hasDraft,
  onClose,
}: {
  filters: Props;
  activeCount: number;
  hasDraft: boolean;
  onClose: () => void;
}) {
  return (
    <div
      id="builder-filters-dropdown"
      className={
        "absolute left-0 z-40 mt-2 max-h-[min(70vh,720px)] w-full max-w-2xl " +
        "overflow-y-auto rounded-xl border border-white/15 bg-gray-950 shadow-2xl"
      }
    >
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <span className="text-sm font-semibold text-white">Suggestion filters</span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={activeCount === 0 && !hasDraft}
            onClick={filters.onClearAll}
            className={
              "text-xs text-gray-400 hover:text-white disabled:cursor-not-allowed " +
              "disabled:opacity-40"
            }
          >
            Clear all
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close filters"
            className="rounded px-2 py-1 text-gray-400 hover:bg-white/10 hover:text-white"
          >
            ×
          </button>
        </div>
      </div>
      <OwnedFilterSection {...filters} />
      <PriceFilterSection {...filters} />
      <TypeFilterSection
        title="Primary type"
        description="Match at least one selected primary type."
        options={PRIMARY_TYPE_OPTIONS}
        selected={filters.cardTypes}
        onChange={filters.onCardTypesChange}
      />
      <TypeFilterSection
        title="Subtype"
        description="Match at least one selected subtype."
        options={SUBTYPE_OPTIONS}
        selected={filters.subtypes}
        onChange={filters.onSubtypesChange}
        last
      />
    </div>
  );
}

function OwnedFilterSection(props: Props) {
  const active = props.selectedCollectionIds.length > 0;
  return (
    <section className="border-b border-white/10 px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            role="switch"
            aria-label="Only cards I own"
            aria-checked={active}
            disabled={props.collections.length === 0}
            onClick={props.onToggleOwnedOnly}
            className={
              "relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full " +
              `transition-colors disabled:opacity-40 ${
                active ? "bg-indigo-600" : "bg-white/10"
              }`
            }
          >
            <span
              className={
                "inline-block h-5 w-5 transform rounded-full bg-white transition-transform " +
                (active ? "translate-x-5" : "translate-x-0.5")
              }
            />
          </button>
          <span className="text-sm font-medium text-white">Only cards I own</span>
        </div>
        {active && (
          <span className="text-xs text-indigo-200">
            {props.selectedCollectionIds.length}/{props.collections.length} collections
          </span>
        )}
      </div>
      {props.collections.length === 0 && (
        <p className="mt-2 text-xs text-gray-500">No collections are available.</p>
      )}
      {active && (
        <>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {props.collections.map((collection) => {
              const checked = props.selectedCollectionIds.includes(collection.id);
              return (
                <button
                  key={collection.id}
                  type="button"
                  aria-pressed={checked}
                  onClick={() => props.onToggleCollection(collection.id)}
                  title={`${collection.card_count} cards`}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                    checked
                      ? "bg-indigo-600 text-white hover:bg-indigo-500"
                      : "bg-white/5 text-gray-400 hover:bg-white/10 hover:text-gray-200"
                  }`}
                >
                  {checked ? "✓ " : ""}
                  {collection.name}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex gap-3">
            <button
              type="button"
              onClick={props.onSelectAllCollections}
              className="text-xs text-gray-400 hover:text-white"
            >
              Select all
            </button>
            <button
              type="button"
              onClick={props.onClearCollections}
              className="text-xs text-gray-400 hover:text-white"
            >
              Turn off
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function PriceFilterSection(props: Props) {
  const active = props.minPriceCents != null || props.maxPriceCents != null;
  return (
    <section className="border-b border-white/10 px-4 py-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Price range (EUR)
          </h3>
          <p className="mt-1 text-xs text-gray-500">
            Nonfoil Scryfall prices for this session. Unpriced cards are excluded.
          </p>
        </div>
        {active && (
          <span className="rounded-full bg-indigo-600/30 px-2 py-0.5 text-xs text-indigo-200">
            €{props.minPriceCents != null ? (props.minPriceCents / 100).toFixed(2) : "0.00"}
            {" – "}
            {props.maxPriceCents != null
              ? `€${(props.maxPriceCents / 100).toFixed(2)}`
              : "∞"}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <PriceInput
          label="Min €"
          value={props.minPriceDraft}
          placeholder="0.00"
          onChange={props.onMinPriceDraftChange}
        />
        <PriceInput
          label="Max €"
          value={props.maxPriceDraft}
          placeholder="No cap"
          onChange={props.onMaxPriceDraftChange}
        />
        <button
          type="button"
          onClick={props.onApplyPrice}
          className={
            "rounded-md bg-indigo-600 px-3 py-2 text-xs font-medium text-white " +
            "hover:bg-indigo-500"
          }
        >
          Apply
        </button>
        {active && (
          <button
            type="button"
            onClick={props.onClearPrice}
            className="px-1 py-2 text-xs text-gray-400 hover:text-white"
          >
            Clear range
          </button>
        )}
      </div>
    </section>
  );
}

function PriceInput({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-xs text-gray-400">
      <span className="mb-1 block">{label}</span>
      <input
        type="number"
        min="0"
        step="0.01"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={
          "w-28 rounded-md border border-white/20 bg-white/10 px-2 py-2 text-sm " +
          "text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
        }
      />
    </label>
  );
}

function TypeFilterSection({
  title,
  description,
  options,
  selected,
  onChange,
  last = false,
}: {
  title: string;
  description: string;
  options: readonly string[];
  selected: string[];
  onChange: (selected: string[]) => void;
  last?: boolean;
}) {
  return (
    <section className={`px-4 py-4 ${last ? "" : "border-b border-white/10"}`}>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">{title}</h3>
      <p className="mt-1 text-xs text-gray-500">{description}</p>
      <div className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {options.map((option) => {
          const active = selected.includes(option);
          return (
            <label
              key={option}
              className={
                "flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 " +
                `text-xs transition-colors ${
                  active
                    ? "border-indigo-500 bg-indigo-600/30 text-indigo-100"
                    : "border-white/10 text-gray-300 hover:border-white/20 hover:text-white"
                }`
              }
            >
              <input
                type="checkbox"
                checked={active}
                onChange={() =>
                  onChange(
                    active ? selected.filter((item) => item !== option) : [...selected, option],
                  )
                }
                className="h-3 w-3 accent-indigo-500"
              />
              {option}
            </label>
          );
        })}
      </div>
    </section>
  );
}
