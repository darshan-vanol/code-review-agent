import type { Severity } from "../api";

const COLORS: Record<Severity, string> = {
  info: "#6b7280",
  low: "#2563eb",
  medium: "#d97706",
  high: "#dc2626",
  critical: "#7f1d1d",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className="badge" style={{ background: COLORS[severity] }}>
      {severity}
    </span>
  );
}
