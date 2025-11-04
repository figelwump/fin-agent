import React from 'react';
import {
  PieChart as RPieChart,
  Pie,
  Cell,
  Tooltip as RTooltip,
  ResponsiveContainer,
  LineChart as RLineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  BarChart as RBarChart,
  Bar,
  Legend,
} from 'recharts';

// Finviz types live client-side only. We keep this intentionally small.
export interface FinvizSpec {
  version: string; // e.g., "1.0"
  spec: {
    type: 'pie' | 'line' | 'bar' | 'table' | 'metric';
    title?: string;
    data?: any[] | Record<string, any>;
    // series configuration
    xKey?: string;
    yKey?: string;
    nameKey?: string; // pie
    valueKey?: string; // pie
    columns?: { key: string; label: string }[]; // table
    options?: {
      currency?: boolean;
      accumulate?: boolean;
    };
  };
}

// Helper: parse finviz JSON safely
export function parseFinviz(text: string): FinvizSpec | null {
  try {
    const obj = JSON.parse(text);
    return obj as FinvizSpec;
  } catch {
    return null;
  }
}

export function isValidFinviz(obj: any): obj is FinvizSpec {
  return (
    obj &&
    typeof obj === 'object' &&
    typeof obj.version === 'string' &&
    obj.spec && typeof obj.spec === 'object' && typeof obj.spec.type === 'string'
  );
}

function formatCurrency(n: any) {
  const num = Number(n);
  if (!isFinite(num)) return String(n);
  return num.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });
}

function Title({ title }: { title?: string }) {
  if (!title) return null;
  return <div className="text-sm font-semibold text-gray-800 mb-2">{title}</div>;
}

function ChartContainer({ children }: { children: React.ReactNode }) {
  // Fixed height works well inside message blocks
  return (
    <div className="w-full bg-white border border-gray-200 p-2">
      <div style={{ width: '100%', height: 260 }}>{children}</div>
    </div>
  );
}

function PieViz({ spec }: { spec: FinvizSpec['spec'] }) {
  const data = Array.isArray(spec.data) ? spec.data : [];
  const nameKey = spec.nameKey || 'name';
  const valueKey = spec.valueKey || 'value';
  const isCurrency = !!spec.options?.currency;
  const colors = ['#0ea5e9', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#f43f5e'];
  return (
    <>
      <Title title={spec.title} />
      <ChartContainer>
        <ResponsiveContainer>
          <RPieChart>
            <Pie data={data} dataKey={valueKey} nameKey={nameKey} outerRadius={80} label>
              {data.map((_, idx) => (
                <Cell key={idx} fill={colors[idx % colors.length]} />
              ))}
            </Pie>
            <RTooltip
              formatter={(value: any) => (isCurrency ? formatCurrency(value) : value)}
            />
            <Legend />
          </RPieChart>
        </ResponsiveContainer>
      </ChartContainer>
    </>
  );
}

function LineViz({ spec }: { spec: FinvizSpec['spec'] }) {
  const data = Array.isArray(spec.data) ? spec.data : [];
  const xKey = spec.xKey || 'x';
  const yKey = spec.yKey || 'y';
  const isCurrency = !!spec.options?.currency;
  return (
    <>
      <Title title={spec.title} />
      <ChartContainer>
        <ResponsiveContainer>
          <RLineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={xKey} />
            <YAxis tickFormatter={(v) => (isCurrency ? formatCurrency(v) : String(v))} />
            <RTooltip formatter={(v: any) => (isCurrency ? formatCurrency(v) : v)} />
            <Line type="monotone" dataKey={yKey} stroke="#0ea5e9" strokeWidth={2} dot={false} />
          </RLineChart>
        </ResponsiveContainer>
      </ChartContainer>
    </>
  );
}

function BarViz({ spec }: { spec: FinvizSpec['spec'] }) {
  const data = Array.isArray(spec.data) ? spec.data : [];
  const xKey = spec.xKey || 'x';
  const yKey = spec.yKey || 'y';
  const isCurrency = !!spec.options?.currency;
  return (
    <>
      <Title title={spec.title} />
      <ChartContainer>
        <ResponsiveContainer>
          <RBarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={xKey} />
            <YAxis tickFormatter={(v) => (isCurrency ? formatCurrency(v) : String(v))} />
            <RTooltip formatter={(v: any) => (isCurrency ? formatCurrency(v) : v)} />
            <Bar dataKey={yKey} fill="#6366f1" />
            <Legend />
          </RBarChart>
        </ResponsiveContainer>
      </ChartContainer>
    </>
  );
}

function TableViz({ spec }: { spec: FinvizSpec['spec'] }) {
  const cols = spec.columns && spec.columns.length > 0 ? spec.columns : [];
  const rows = Array.isArray(spec.data) ? spec.data : [];
  const isCurrency = !!spec.options?.currency;
  return (
    <div className="bg-white border border-gray-200">
      <Title title={spec.title} />
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {cols.map((c) => (
                <th key={c.key} className="text-left px-2 py-1 font-semibold text-gray-700">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r: any, i: number) => (
              <tr key={i} className="border-b border-gray-100">
                {cols.map((c) => {
                  const v = r[c.key];
                  return (
                    <td key={c.key} className="px-2 py-1 text-gray-800">
                      {isCurrency && typeof v === 'number' ? formatCurrency(v) : String(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MetricViz({ spec }: { spec: FinvizSpec['spec'] }) {
  const value = (spec as any)?.value ?? null;
  const isCurrency = !!spec.options?.currency;
  const display = isCurrency ? formatCurrency(value) : String(value);
  return (
    <div className="bg-white border border-gray-200 p-3">
      <Title title={spec.title} />
      <div className="text-2xl font-semibold text-gray-900">{display}</div>
    </div>
  );
}

export function VizRenderer({ viz }: { viz: FinvizSpec }) {
  const spec = viz.spec;
  switch (spec.type) {
    case 'pie':
      return <PieViz spec={spec} />;
    case 'line':
      return <LineViz spec={spec} />;
    case 'bar':
      return <BarViz spec={spec} />;
    case 'table':
      return <TableViz spec={spec} />;
    case 'metric':
      return <MetricViz spec={spec} />;
    default:
      return (
        <pre className="text-xs bg-white p-2 border border-gray-200 overflow-x-auto font-mono">
{JSON.stringify(viz, null, 2)}
        </pre>
      );
  }
}

