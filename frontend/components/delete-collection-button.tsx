"use client";

import { useState } from "react";
import { apiClient } from "@/lib/api";

interface DeleteCollectionButtonProps {
  collectionId: string;
  collectionName: string;
  onDeleted: () => void;
}

export function DeleteCollectionButton({
  collectionId,
  collectionName,
  onDeleted,
}: DeleteCollectionButtonProps) {
  const [deleting, setDeleting] = useState(false);

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (
      !confirm(
        `Delete "${collectionName}"? All cards in this collection will be permanently removed.`,
      )
    )
      return;
    setDeleting(true);
    try {
      await apiClient.deleteCollection(collectionId);
      onDeleted();
    } catch {
      alert("Failed to delete collection");
      setDeleting(false);
    }
  }

  return (
    <button
      onClick={(e) => void handleDelete(e)}
      disabled={deleting}
      title="Delete collection"
      className="absolute right-2 top-2 rounded-md bg-black/40 p-1.5 text-gray-400 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100 disabled:opacity-50"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 16 16"
        fill="currentColor"
        className="h-3.5 w-3.5"
      >
        <path
          fillRule="evenodd"
          d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35l.815-8.15h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5a.75.75 0 0 1 .786-.711Z"
          clipRule="evenodd"
        />
      </svg>
    </button>
  );
}
