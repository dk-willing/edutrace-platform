"use client";

import { useState } from "react";

export function LoadingButton({ children, onClick, disabled, ...props }) {
  const [loading, setLoading] = useState(false);

  async function handleClick(event) {
    setLoading(true);
    try {
      await onClick?.(event);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button {...props} disabled={disabled || loading} onClick={handleClick}>
      {loading ? "Loading..." : children}
    </button>
  );
}
