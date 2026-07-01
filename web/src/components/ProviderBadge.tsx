import { useEffect, useState } from "react";

import { getVersion, type VersionInfo } from "../api";

/**
 * Small always-visible indicator of the provider and model the API is
 * configured to run reviews with. Fetched once on mount from GET /version so
 * it's visible before, during, and after a review. Renders nothing until the
 * fetch resolves (and stays hidden if it fails, since it's non-essential chrome).
 */
export function ProviderBadge() {
  const [info, setInfo] = useState<VersionInfo | null>(null);

  useEffect(() => {
    let alive = true;
    getVersion()
      .then((v) => alive && setInfo(v))
      .catch(() => {
        /* non-essential; leave the badge hidden on failure */
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!info) return null;

  return (
    <span
      className="provider-badge"
      title={`Reviews run with the ${info.provider} provider using model ${info.model}`}
    >
      <span className="provider-badge-label">provider</span>
      <span className="provider-badge-provider">{info.provider}</span>
      <span className="provider-badge-sep">·</span>
      <span className="provider-badge-model">{info.model}</span>
    </span>
  );
}
