"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { getCardImage, primeCardImage } from "@/lib/card-image-cache";

interface CardHoverProps {
  name: string;
  imageUri?: string | null;
  children: ReactNode;
  className?: string;
}

const HOVER_DELAY_MS = 150;
const PREVIEW_WIDTH = 256;
const PREVIEW_HEIGHT = 358;
const VIEWPORT_PADDING = 12;

interface Position {
  top: number;
  left: number;
}

/**
 * Wrap any text rendering of a card name to show a floating preview of the
 * card image on hover (desktop) or tap (touch).
 *
 * Callers that already have the image URL should pass ``imageUri`` to avoid a
 * network round-trip; otherwise the cache lazily resolves via the fuzzy card
 * search endpoint.
 */
export function CardHover({ name, imageUri, children, className }: CardHoverProps) {
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const showTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [open, setOpen] = useState(false);
  const [resolvedUri, setResolvedUri] = useState<string | null>(imageUri ?? null);
  const [position, setPosition] = useState<Position | null>(null);
  const [imageFailed, setImageFailed] = useState(false);

  const isTouch = useMemo(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(hover: none)").matches;
  }, []);

  useEffect(() => {
    if (imageUri) {
      primeCardImage(name, imageUri);
      setResolvedUri(imageUri);
    }
  }, [name, imageUri]);

  const computePosition = useCallback((): Position => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return { top: 0, left: 0 };
    const spaceRight = window.innerWidth - rect.right;
    const left =
      spaceRight >= PREVIEW_WIDTH + VIEWPORT_PADDING
        ? rect.right + 8
        : Math.max(VIEWPORT_PADDING, rect.left - PREVIEW_WIDTH - 8);
    const rawTop = rect.top + rect.height / 2 - PREVIEW_HEIGHT / 2;
    const top = Math.min(
      Math.max(VIEWPORT_PADDING, rawTop),
      window.innerHeight - PREVIEW_HEIGHT - VIEWPORT_PADDING,
    );
    return { top, left };
  }, []);

  const reveal = useCallback(async () => {
    setPosition(computePosition());
    setOpen(true);
    if (!resolvedUri) {
      const uri = await getCardImage(name);
      setResolvedUri(uri);
      if (!uri) setImageFailed(true);
    }
  }, [computePosition, name, resolvedUri]);

  const handleEnter = useCallback(() => {
    if (isTouch) return;
    if (showTimer.current) clearTimeout(showTimer.current);
    showTimer.current = setTimeout(() => {
      void reveal();
    }, HOVER_DELAY_MS);
  }, [isTouch, reveal]);

  const handleLeave = useCallback(() => {
    if (isTouch) return;
    if (showTimer.current) {
      clearTimeout(showTimer.current);
      showTimer.current = null;
    }
    setOpen(false);
  }, [isTouch]);

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLSpanElement>) => {
      if (!isTouch) return;
      // Prevent the parent (often a clickable row) from also handling the tap
      // — the user explicitly targeted a card name to preview it.
      e.stopPropagation();
      if (open) {
        setOpen(false);
        return;
      }
      void reveal();
    },
    [isTouch, open, reveal],
  );

  useEffect(() => {
    if (!open || !isTouch) return;
    const onDocClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, [open, isTouch]);

  useEffect(() => {
    return () => {
      if (showTimer.current) clearTimeout(showTimer.current);
    };
  }, []);

  return (
    <span
      ref={wrapRef}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      onClick={handleClick}
      className={className}
    >
      {children}
      {open && position ? (
        <span
          aria-hidden
          style={{
            position: "fixed",
            top: position.top,
            left: position.left,
            width: PREVIEW_WIDTH,
            zIndex: 60,
            pointerEvents: "none",
          }}
        >
          {resolvedUri && !imageFailed ? (
            <img
              src={resolvedUri}
              alt=""
              onError={() => setImageFailed(true)}
              className="w-full rounded-[4.5%] shadow-2xl ring-1 ring-black/40"
            />
          ) : (
            <span className="block rounded-lg border border-white/10 bg-zinc-900/95 px-3 py-2 text-xs text-gray-300 shadow-2xl">
              {name}
              {imageFailed ? " — image unavailable" : "…"}
            </span>
          )}
        </span>
      ) : null}
    </span>
  );
}
