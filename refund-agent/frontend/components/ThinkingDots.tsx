// Three bouncing dots used as the agent's "thinking" indicator.
// Pure CSS animation (Tailwind keyframe) — no JS, no extra dependencies.

const DELAYS = ["0ms", "150ms", "300ms"] as const;

interface ThinkingDotsProps {
  /** Visually-hidden label exposed to assistive technologies. */
  label?: string;
}

export function ThinkingDots({
  label = "Penny is thinking",
}: ThinkingDotsProps): JSX.Element {
  return (
    <span
      role="status"
      aria-label={label}
      className="inline-flex items-end gap-1"
    >
      {DELAYS.map((delay) => (
        <span
          key={delay}
          className="block h-1.5 w-1.5 rounded-full bg-sky-500 animate-thinking-dot"
          style={{ animationDelay: delay }}
        />
      ))}
    </span>
  );
}
