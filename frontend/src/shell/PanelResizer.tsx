// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * The width of the left panel, beside the page: its right edge is a separator
 * that a pointer drags and the arrow keys move, between `MIN_WIDTH` and
 * `MAX_SHARE` of the window. The width is remembered per browser
 * (`PANEL_WIDTH_KEY`). It mirrors the right panel's (`SidePanel`).
 */
import {
  type KeyboardEvent,
  type PointerEvent,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { remember, remembered } from "./storage";

/** The width, in CSS pixels, per browser. */
export const PANEL_WIDTH_KEY = "panel.width";

export const MIN_WIDTH = 220;
export const DEFAULT_WIDTH = 280;
/** The most of the window it may take. */
export const MAX_SHARE = 0.4;
/** How far one arrow key moves the edge. */
export const STEP = 16;

function clamp(width: number, max: number): number {
  return Math.round(Math.min(Math.max(width, MIN_WIDTH), max));
}

function rememberedWidth(): number {
  const width = Number(remembered(PANEL_WIDTH_KEY) ?? Number.NaN);
  return Number.isFinite(width) && width > 0 ? width : DEFAULT_WIDTH;
}

function subscribeToResize(changed: () => void): () => void {
  window.addEventListener("resize", changed);
  return () => {
    window.removeEventListener("resize", changed);
  };
}

function useViewportWidth(): number {
  return useSyncExternalStore(
    subscribeToResize,
    () => window.innerWidth,
    () => 1024,
  );
}

/** The width the panel is drawn at, held inside the window as it is now. */
export function usePanelWidth(): {
  shown: number;
  max: number;
  resizeTo: (next: number, keep: boolean) => void;
} {
  const [width, setWidth] = useState(rememberedWidth);
  const max = Math.max(MIN_WIDTH, Math.floor(useViewportWidth() * MAX_SHARE));
  return {
    shown: clamp(width, max),
    max,
    resizeTo: (next, keep) => {
      const clamped = clamp(next, max);
      setWidth(clamped);
      if (keep) remember(PANEL_WIDTH_KEY, String(clamped));
    },
  };
}

/**
 * The right edge, which a pointer drags and the arrow keys move.
 *
 * The edge being on the panel's right, Right widens it and Left narrows it.
 * Home and End go to the two ends.
 */
export function PanelResizer({
  id,
  width,
  max,
  onResize,
}: Readonly<{
  id: string;
  width: number;
  max: number;
  onResize: (width: number, keep: boolean) => void;
}>) {
  const dragStart = useRef<{ x: number; width: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const follow = (event: PointerEvent<HTMLDivElement>, keep: boolean) => {
    const from = dragStart.current;
    if (from === null) return;
    onResize(from.width + (event.clientX - from.x), keep);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = new Map([
      ["ArrowRight", width + STEP],
      ["ArrowLeft", width - STEP],
      ["Home", MIN_WIDTH],
      ["End", max],
    ]).get(event.key);
    if (next === undefined) return;
    event.preventDefault();
    onResize(next, true);
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the panel"
      aria-controls={id}
      aria-valuemin={MIN_WIDTH}
      aria-valuemax={max}
      aria-valuenow={width}
      tabIndex={0}
      data-dragging={dragging}
      className="panel-resize"
      onKeyDown={onKeyDown}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        dragStart.current = { x: event.clientX, width };
        setDragging(true);
        try {
          event.currentTarget.setPointerCapture(event.pointerId);
        } catch {
          // No capture (an old browser, a test without layout): the drag
          // still follows the pointer while it is over the edge.
        }
      }}
      onPointerMove={(event) => {
        follow(event, false);
      }}
      onPointerUp={(event) => {
        follow(event, true);
        dragStart.current = null;
        setDragging(false);
      }}
      onPointerCancel={() => {
        onResize(width, true);
        dragStart.current = null;
        setDragging(false);
      }}
    />
  );
}
