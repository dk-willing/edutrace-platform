"use client";

import { useState } from "react";

export function LoadingButton({
  children,
  onClick,
  disabled,
  loading: controlledLoading,
  ...props
}) {
  const [internalLoading, setInternalLoading] = useState(false);
  const loading = controlledLoading ?? internalLoading;

  async function handleClick(event) {
    if (!onClick) return;
    setInternalLoading(true);
    try {
      await onClick(event);
    } finally {
      setInternalLoading(false);
    }
  }

  return (
    <button {...props} disabled={disabled || loading} onClick={handleClick}>
      {loading && <span className="button-spinner" aria-hidden="true" />}
      <span>{loading ? "Loading..." : children}</span>
    </button>
  );
}
