import {
  CartesianGrid,
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

const FAITHFULNESS = "#5b8cff";
const CORRECTNESS = "#35c08a";

export function TrendChart({ reports }: { reports: EvalReportSummary[] }) {
  const data = reports.map((r) => ({
    id: `run ${r.id}`,
    Faithfulness: r.aggregate.faithfulness,
    "Answer correctness": r.aggregate.answer_correctness,
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
        <CartesianGrid stroke="#1b2536" vertical={false} />
        <XAxis dataKey="id" stroke="#5d6b7e" tickLine={false} axisLine={false} />
        <YAxis domain={[0, 1]} stroke="#5d6b7e" tickLine={false} axisLine={false} />
        <Tooltip
          contentStyle={{
            background: "#121926",
            border: "1px solid #233044",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#8a99ad" }}
        />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        <ReferenceLine
          y={0.75}
          stroke="#e0a63c"
          strokeDasharray="4 4"
          label={{ value: "pass bar 0.75", position: "insideTopRight", fill: "#e0a63c", fontSize: 11 }}
        />
        <Line type="monotone" dataKey="Faithfulness" stroke={FAITHFULNESS} strokeWidth={2} dot={{ r: 4 }} />
        <Line
          type="monotone"
          dataKey="Answer correctness"
          stroke={CORRECTNESS}
          strokeWidth={2}
          dot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
