/**
 * The mark is the airlock itself, seen head on: a chamber, two door leaves and
 * the amber seal down the middle. Nothing else in the product uses this shape.
 */
export function Wordmark() {
  return (
    <div className="flex items-center gap-2.5">
      <svg
        viewBox="0 0 20 20"
        width="22"
        height="22"
        aria-hidden="true"
        className="shrink-0 text-ink-dim"
      >
        <rect
          x="1"
          y="1"
          width="18"
          height="18"
          rx="1.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
        />
        <path d="M4.4 4.4h4.9v11.2H4.4z" fill="currentColor" opacity="0.24" />
        <path d="M10.7 4.4h4.9v11.2h-4.9z" fill="currentColor" opacity="0.24" />
        <rect x="9.45" y="4.4" width="1.1" height="11.2" fill="#F2A93B" />
      </svg>
      <span className="flex flex-col leading-none">
        <h1 className="text-[17px] font-semibold tracking-[-0.02em] text-ink">Airlock</h1>
        <span className="label-micro mt-[3px] text-ink-faint">Reviewer console</span>
      </span>
    </div>
  );
}
