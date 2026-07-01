import type { Span } from "../api";

export function SpansPanel({ spans }: { spans: Span[] }) {
  if (spans.length === 0) return null;
  return (
    <details className="spans">
      <summary>Node spans ({spans.length})</summary>
      <table>
        <thead>
          <tr>
            <th>node</th>
            <th>model</th>
            <th>latency (ms)</th>
            <th>in tok</th>
            <th>out tok</th>
          </tr>
        </thead>
        <tbody>
          {spans.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td>{s.model ?? "—"}</td>
              <td>{s.latency_ms.toFixed(1)}</td>
              <td>{s.input_tokens}</td>
              <td>{s.output_tokens}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
