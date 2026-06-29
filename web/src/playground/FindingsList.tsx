import type { Finding } from "../api";
import { SeverityBadge } from "../components/SeverityBadge";

function groupByFile(findings: Finding[]): Record<string, Finding[]> {
  const groups: Record<string, Finding[]> = {};
  for (const f of findings) {
    (groups[f.file] ??= []).push(f);
  }
  return groups;
}

export function FindingsList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <p className="empty">No issues found.</p>;
  }
  const groups = groupByFile(findings);
  return (
    <div className="findings">
      {Object.entries(groups).map(([file, items]) => (
        <section key={file} className="file-group">
          <h3>{file}</h3>
          <ul>
            {items.map((f, i) => (
              <li key={i} className={`finding cat-${f.category}`}>
                <div className="finding-head">
                  <SeverityBadge severity={f.severity} />
                  <span className="loc">
                    {`${f.file}:${f.line_start}-${f.line_end}`}
                  </span>
                  <span className="cat">{f.category}</span>
                </div>
                <p className="msg">{f.message}</p>
                <p className="suggestion">{f.suggestion}</p>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
