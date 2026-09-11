/* eslint-disable @next/next/no-img-element */
// Penny uses the Bluey avatar from the alohe/avatars CDN. A plain <img> with
// explicit width/height and lazy loading is the lightest possible approach —
// the browser caches the file across every place we render the avatar.

import type { CSSProperties } from "react";

const AVATAR_SRC =
  "https://cdn.jsdelivr.net/gh/alohe/avatars/png/bluey_2.png";

interface PennyAvatarProps {
  /** Rendered size in CSS pixels (square). Default 40. */
  size?: number;
  /** Show a small pulsing online dot in the corner. */
  online?: boolean;
  /** Load eagerly (use for above-the-fold header avatars only). */
  priority?: boolean;
  className?: string;
}

export function PennyAvatar({
  size = 40,
  online = false,
  priority = false,
  className = "",
}: PennyAvatarProps): JSX.Element {
  const containerStyle: CSSProperties = { width: size, height: size };
  const dotSize = Math.max(8, Math.round(size * 0.22));

  return (
    <span
      className={`relative inline-flex shrink-0 ${className}`}
      style={containerStyle}
      aria-hidden="true"
    >
      <img
        src={AVATAR_SRC}
        alt=""
        width={size}
        height={size}
        loading={priority ? "eager" : "lazy"}
        decoding="async"
        draggable={false}
        className="h-full w-full select-none rounded-full bg-sky-50 object-cover ring-2 ring-white shadow-sm"
      />
      {online && (
        <span
          className="absolute bottom-0 right-0 block rounded-full bg-emerald-400 ring-2 ring-white animate-pulse"
          style={{ width: dotSize, height: dotSize }}
        />
      )}
    </span>
  );
}

interface PennyMascotProps {
  size?: number;
  /** Apply a gentle floating animation (login hero). */
  animated?: boolean;
}

export function PennyMascot({
  size = 96,
  animated = true,
}: PennyMascotProps): JSX.Element {
  return (
    <div className="flex flex-col items-center">
      <div
        className={`rounded-full bg-white p-2 shadow-md ring-1 ring-sky-100 ${
          animated ? "animate-float" : ""
        }`}
      >
        <PennyAvatar size={size} priority />
      </div>
    </div>
  );
}
