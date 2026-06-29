import {
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EvalReportSummary } from "../api";

export function TrendChart({ reports }: { reports: EvalReportSummary[] }) {
  const data = reports.map((r) => ({
    id: r.id,
    faithfulness: r.aggregate.faithfulness,
    answer_correctness: r.aggregate.answer_correctness,
  }));
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}>
        <XAxis dataKey="id" />
        <YAxis domain={[0, 1]} />
        <Tooltip />
        <Legend />
        <ReferenceLine y={0.75} stroke="#dc2626" strokeDasharray="4 4" label="0.75" />
        <Line type="monotone" dataKey="faithfulness" stroke="#2563eb" />
        <Line type="monotone" dataKey="answer_correctness" stroke="#059669" />
      </LineChart>
    </ResponsiveContainer>
  );
}
