/** Text only, one weight up from the interface, nothing drawn around it. */
export function Wordmark() {
  return (
    <div className="flex items-baseline gap-2">
      <h1 className="text-[15px] font-medium leading-none text-ink">Airlock</h1>
      <span className="hidden text-[12px] leading-none text-ink-soft sm:inline">
        Reviewer console
      </span>
    </div>
  );
}
