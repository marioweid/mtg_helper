"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { apiClient } from "@/lib/api";
import type { CardExportPreview, CollectionResponse, ExportCard } from "@/lib/types";

interface Props {
  title: string;
  cards: ExportCard[];
  onClose: () => void;
}

function useExportPreview(cards: ExportCard[], collectionIds: string[]) {
  const key = JSON.stringify([cards, collectionIds]);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({
    key: "",
    loading: true,
    error: "",
    collections: [] as CollectionResponse[],
    preview: null as CardExportPreview | null,
  });
  useEffect(() => {
    let active = true;
    setState((previous) => ({ ...previous, key, loading: true, error: "", preview: null }));
    const [requestedCards, requestedIds] = JSON.parse(key) as [ExportCard[], string[]];
    void Promise.all([
      apiClient.listCollections(),
      apiClient.previewCardExport(requestedCards, requestedIds),
    ])
      .then(([collections, preview]) => {
        if (active) setState({ key, loading: false, error: "", collections, preview });
      })
      .catch((error: unknown) => {
        if (active)
          setState((previous) => ({
            ...previous,
            key,
            loading: false,
            preview: null,
            error: error instanceof Error ? error.message : "Export preview failed",
          }));
      });
    return () => {
      active = false;
    };
  }, [key, attempt]);
  return {
    ...state,
    pending: state.loading || state.key !== key,
    retry: () => setAttempt((value) => value + 1),
  };
}

export function CardExportDialog({ title, cards, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [collectionIds, setCollectionIds] = useState<string[]>([]);
  const [format, setFormat] = useState("mtgo");
  const data = useExportPreview(cards, collectionIds);
  useLayoutEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    return () => {
      element?.close();
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  const toggle = (id: string) =>
    setCollectionIds((ids) =>
      ids.includes(id) ? ids.filter((value) => value !== id) : [...ids, id],
    );
  const dismiss = () => {
    // Native focus restoration needs the dialog to still be mounted when it closes.
    dialog.current?.close();
    onClose();
  };

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        dismiss();
      }}
      className={`m-auto max-h-[90dvh] w-[min(56rem,95vw)] overflow-y-auto rounded-xl
        border border-white/15 bg-zinc-950 p-5 text-gray-200 shadow-2xl backdrop:bg-black/75`}
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 id={titleId} className="text-lg font-semibold text-white">
            {title}
          </h2>
          <p className="mt-1 text-xs text-gray-400">
            Read-only preview. No cards are moved or reserved.
          </p>
        </div>
        <button type="button" onClick={dismiss} className="rounded px-2 py-1 hover:bg-white/10">
          Close
        </button>
      </header>
      <label className="mt-4 flex items-center gap-3 text-sm">
        Export format
        <select
          value={format}
          onChange={(event) => setFormat(event.target.value)}
          className="rounded border border-white/15 bg-zinc-900 px-3 py-2"
        >
          <option value="mtgo">MTGO text (.txt)</option>
          <option value="cardmarket">Cardmarket buy list (.txt)</option>
        </select>
      </label>
      <p className="mt-1 text-xs text-gray-500">
        Both use plain quantity + card name, one card per line.
      </p>
      <BinderSelection
        collections={data.collections}
        selectedIds={collectionIds}
        onToggle={toggle}
        onSelect={setCollectionIds}
      />
      {data.pending ? (
        <p role="status" className="mt-4 text-sm">
          Loading export preview…
        </p>
      ) : null}
      {data.error && (
        <div role="alert" className="mt-4 text-sm text-red-300">
          {data.error}{" "}
          <button type="button" onClick={data.retry} className="underline">
            Retry
          </button>
        </div>
      )}
      {!data.pending && data.preview && <ExportPreview preview={data.preview} />}
      <ExportActions
        key={`${format}:${data.key}`}
        format={format}
        text={!data.pending && !data.error ? (data.preview?.text ?? "") : ""}
      />
    </dialog>
  );
}

function BinderSelection({
  collections,
  selectedIds,
  onToggle,
  onSelect,
}: {
  collections: CollectionResponse[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  onSelect: (ids: string[]) => void;
}) {
  return (
    <fieldset className="mt-5 rounded-lg border border-white/10 p-3">
      <legend className="px-1 text-sm font-medium">Subtract cards from selected binders</legend>
      <p className="text-xs text-gray-400">
        None selected = full quantities. Leave proxy binders unchecked when buying real cards.
      </p>
      <div className="my-2 flex gap-3 text-xs text-indigo-300">
        <button type="button" onClick={() => onSelect(collections.map((item) => item.id))}>
          Select all
        </button>
        <button type="button" onClick={() => onSelect([])}>
          Select none
        </button>
      </div>
      <div className="grid max-h-40 gap-2 overflow-y-auto sm:grid-cols-2">
        {collections.map((collection) => (
          <label key={collection.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={selectedIds.includes(collection.id)}
              onChange={() => onToggle(collection.id)}
              className="accent-indigo-500"
            />
            {collection.name}
          </label>
        ))}
      </div>
      {collections.length === 0 && <p className="text-xs text-gray-500">No binders loaded.</p>}
    </fieldset>
  );
}

export function ExportPreview({ preview }: { preview: CardExportPreview }) {
  const summary = [
    `${preview.needed_quantity} copies needed`,
    `${preview.from_binders_quantity} from binders`,
    `${preview.export_quantity} to export`,
  ].join(" · ");
  return (
    <section className="mt-4" aria-label="Export preview">
      <p className="text-sm font-medium text-indigo-200">{summary}</p>
      <p className="mt-1 text-xs text-gray-400">
        Estimated remaining cost: €{(preview.known_price_eur_cents / 100).toFixed(2)}
        {preview.unpriced_quantity > 0 &&
          ` + ${preview.unpriced_quantity} copies without EUR prices`}
        . Indicative card prices, excluding shipping.
      </p>
      <div className="mt-3 max-h-64 overflow-auto rounded border border-white/10">
        <table className="w-full text-left text-xs">
          <caption className="sr-only">
            Quantities needed, available in selected binders and remaining to export
          </caption>
          <thead className="sticky top-0 bg-zinc-900 text-gray-400">
            <tr>
              <th scope="col" className="p-2">
                Card / pull list
              </th>
              <th scope="col" className="p-2">
                Needed
              </th>
              <th scope="col" className="p-2">
                Available
              </th>
              <th scope="col" className="p-2">
                Exporting
              </th>
            </tr>
          </thead>
          <tbody>
            {preview.rows.map((row) => (
              <tr key={row.card_id} className="border-t border-white/5">
                <th scope="row" className="p-2 font-normal">
                  <span className="text-white">{row.name}</span>
                  {row.pulls.length > 0 && (
                    <span className="mt-1 block text-emerald-300">
                      Pull:{" "}
                      {row.pulls.map((pull) => `${pull.quantity} from ${pull.name}`).join("; ")}
                    </span>
                  )}
                </th>
                <td className="p-2 tabular-nums">{row.needed_quantity}</td>
                <td className="p-2 tabular-nums">{row.available_quantity}</td>
                <td className="p-2 font-medium tabular-nums text-indigo-200">
                  {row.export_quantity}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {preview.export_quantity === 0 && (
        <p className="mt-3 text-sm text-emerald-300">
          Nothing to export: no cards selected, or selected binders cover every needed copy.
        </p>
      )}
      {preview.text && (
        <label className="mt-3 block text-xs text-gray-400">
          Export text
          <textarea
            readOnly
            value={preview.text}
            rows={4}
            className={`mt-1 w-full rounded border border-white/10 bg-black/40
              p-2 font-mono text-gray-200`}
          />
        </label>
      )}
    </section>
  );
}

function ExportActions({ text, format }: { text: string; format: string }) {
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function copy() {
    setError("");
    setMessage("");
    try {
      await navigator.clipboard.writeText(text);
      setMessage("Card list copied.");
    } catch {
      setError("Clipboard unavailable. Download the TXT or copy the export text above.");
    }
  }
  function download() {
    setError("");
    setMessage("");
    try {
      const url = URL.createObjectURL(
        new Blob([`${text}\n`], { type: "text/plain;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `${format}-cards.txt`;
      link.click();
      URL.revokeObjectURL(url);
      setMessage("TXT download started.");
    } catch {
      setError("Download failed. Copy the export text above instead.");
    }
  }
  return (
    <footer className="mt-4 flex flex-wrap items-center justify-end gap-3 text-sm">
      <span role="status" className="text-emerald-300">
        {message}
      </span>
      {error && (
        <span role="alert" className="text-red-300">
          {error}
        </span>
      )}
      <button
        type="button"
        disabled={!text}
        onClick={() => void copy()}
        className="rounded-lg border border-white/15 px-3 py-2 disabled:opacity-40"
      >
        Copy list
      </button>
      <button
        type="button"
        disabled={!text}
        onClick={download}
        className="rounded-lg bg-indigo-600 px-3 py-2 text-white disabled:opacity-40"
      >
        Download .txt
      </button>
    </footer>
  );
}
