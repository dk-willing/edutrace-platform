export function PageSkeleton({ rows = 3, cards = 4 }) {
  return (
    <div className="loading-state" aria-label="Loading" role="status">
      <div className="skeleton-grid">
        {Array.from({ length: cards }, (_, index) => (
          <div className="skeleton-card" key={index}>
            <span className="skeleton-line skeleton-label" />
            <span className="skeleton-line skeleton-value" />
            <span className="skeleton-line skeleton-short" />
          </div>
        ))}
      </div>
      <div className="skeleton-panel">
        <span className="skeleton-line skeleton-heading" />
        {Array.from({ length: rows }, (_, index) => (
          <span className="skeleton-row" key={index} />
        ))}
      </div>
    </div>
  );
}
