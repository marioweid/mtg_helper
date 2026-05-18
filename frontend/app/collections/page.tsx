"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { DeleteCollectionButton } from "@/components/delete-collection-button";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { apiClient, ApiError } from "@/lib/api";
import type { CollectionResponse } from "@/lib/types";

export default function CollectionsPage() {
  const toast = useToast();
  const [collections, setCollections] = useState<CollectionResponse[] | null>(null);

  const load = useCallback(async () => {
    try {
      const items = await apiClient.listCollections();
      setCollections(items);
    } catch (err) {
      toast.push(
        err instanceof ApiError ? err.message : "Failed to load collections.",
        "error",
      );
      setCollections([]);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Your Collections"
        subtitle="Track your physical cards and bind them to deck suggestions."
        actions={
          <Link
            href="/collections/new"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
          >
            New Collection
          </Link>
        }
      />

      {collections === null ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[4/5] w-full rounded-xl" />
          ))}
        </div>
      ) : collections.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-white/20 py-20 text-center">
          <p className="text-gray-400">No collections yet.</p>
          <Link
            href="/collections/new"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
          >
            Create your first collection
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {collections.map((c) => (
            <CollectionTile key={c.id} collection={c} onDeleted={() => void load()} />
          ))}
        </div>
      )}
    </div>
  );
}

function CollectionTile({
  collection,
  onDeleted,
}: {
  collection: CollectionResponse;
  onDeleted: () => void;
}) {
  return (
    <div className="group relative">
      <Link
        href={`/collections/${collection.id}`}
        aria-label={`Open collection ${collection.name}`}
        className="relative flex aspect-[4/5] flex-col justify-between overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-indigo-950/50 via-zinc-900 to-zinc-950 p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-white/30 hover:shadow-xl hover:shadow-indigo-900/40"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(99,102,241,0.18),transparent_60%)]" />

        <div className="relative">
          <p className="text-xs uppercase tracking-wider text-indigo-300/80">Collection</p>
          <h2 className="mt-2 pr-8 text-xl font-semibold leading-tight text-white">
            {collection.name}
          </h2>
        </div>

        <div className="relative mt-auto">
          <p className="text-4xl font-bold tabular-nums text-white">
            {collection.card_count}
          </p>
          <p className="text-xs text-gray-400">
            card{collection.card_count !== 1 ? "s" : ""}
          </p>
          <p className="mt-3 text-[11px] text-gray-500">
            Created {new Date(collection.created_at).toLocaleDateString()}
          </p>
        </div>
      </Link>
      <DeleteCollectionButton
        collectionId={collection.id}
        collectionName={collection.name}
        onDeleted={onDeleted}
      />
    </div>
  );
}
