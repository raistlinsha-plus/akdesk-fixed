import { useState, type FormEvent } from "react";
import { Calculator, CheckCircle2 } from "lucide-react";
import { apiPost } from "../api";
import { formatNumber, Panel } from "../components/UI";
import type { CalculatorResult } from "../types";

const today = new Date();
const maturity = new Date();
maturity.setFullYear(today.getFullYear() + 5);

function isoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function CalculatorPage() {
  const [form, setForm] = useState({
    settlement_date: isoDate(today),
    maturity_date: isoDate(maturity),
    coupon_rate_pct: "2.50",
    clean_price: "100.00",
    face_value: "100",
    frequency: "2",
    day_count: "ACT/365",
    position_face_value: "1000000",
  });
  const [result, setResult] = useState<CalculatorResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function setField(name: string, value: string) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await apiPost<CalculatorResult>("/calculators/bond", {
        settlement_date: form.settlement_date,
        maturity_date: form.maturity_date,
        coupon_rate_pct: Number(form.coupon_rate_pct),
        clean_price: Number(form.clean_price),
        face_value: Number(form.face_value),
        frequency: Number(form.frequency),
        day_count: form.day_count,
        position_face_value: Number(form.position_face_value),
      });
      setResult(response);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "计算失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <header className="page-heading">
        <div>
          <span className="eyebrow">BOND ANALYTICS</span>
          <h1>固收计算器</h1>
          <p>固定利率债的价格、YTM、久期、凸性和 DV01</p>
        </div>
      </header>

      <div className="calculator-layout">
        <Panel title="债券参数" eyebrow="INPUT">
          <form className="calculator-form" onSubmit={submit}>
            <label>
              <span>结算日</span>
              <input
                type="date"
                value={form.settlement_date}
                onChange={(event) =>
                  setField("settlement_date", event.target.value)
                }
              />
            </label>
            <label>
              <span>到期日</span>
              <input
                type="date"
                value={form.maturity_date}
                onChange={(event) =>
                  setField("maturity_date", event.target.value)
                }
              />
            </label>
            <label>
              <span>票面利率（%）</span>
              <input
                type="number"
                step="0.001"
                value={form.coupon_rate_pct}
                onChange={(event) =>
                  setField("coupon_rate_pct", event.target.value)
                }
              />
            </label>
            <label>
              <span>净价</span>
              <input
                type="number"
                step="0.001"
                value={form.clean_price}
                onChange={(event) =>
                  setField("clean_price", event.target.value)
                }
              />
            </label>
            <label>
              <span>面值</span>
              <input
                type="number"
                step="1"
                value={form.face_value}
                onChange={(event) =>
                  setField("face_value", event.target.value)
                }
              />
            </label>
            <label>
              <span>年付息次数</span>
              <select
                value={form.frequency}
                onChange={(event) =>
                  setField("frequency", event.target.value)
                }
              >
                <option value="1">1 次</option>
                <option value="2">2 次</option>
                <option value="4">4 次</option>
                <option value="12">12 次</option>
              </select>
            </label>
            <label>
              <span>计息日规则</span>
              <select
                value={form.day_count}
                onChange={(event) =>
                  setField("day_count", event.target.value)
                }
              >
                <option value="ACT/365">ACT/365</option>
                <option value="ACT/ACT">ACT/ACT</option>
                <option value="30/360">30/360</option>
              </select>
            </label>
            <label className="span-2">
              <span>头寸面值（用于 DV01）</span>
              <input
                type="number"
                step="10000"
                value={form.position_face_value}
                onChange={(event) =>
                  setField("position_face_value", event.target.value)
                }
              />
            </label>
            {error ? <div className="form-error span-2">{error}</div> : null}
            <button className="primary-button span-2" disabled={loading}>
              <Calculator size={17} />
              {loading ? "正在计算…" : "计算债券指标"}
            </button>
          </form>
        </Panel>

        <Panel title="计算结果" eyebrow="OUTPUT">
          {result ? (
            <div className="result-stack">
              <div className="result-hero">
                <span>到期收益率 YTM</span>
                <strong>{formatNumber(result.ytm_pct, 4)}%</strong>
                <small>
                  全价 {formatNumber(result.dirty_price, 5)} · 应计利息{" "}
                  {formatNumber(result.accrued_interest, 5)}
                </small>
              </div>
              <div className="result-grid">
                <ResultMetric
                  label="麦考利久期"
                  value={result.macaulay_duration}
                  suffix=" 年"
                />
                <ResultMetric
                  label="修正久期"
                  value={result.modified_duration}
                  suffix=" 年"
                />
                <ResultMetric
                  label="凸性"
                  value={result.convexity}
                  suffix=""
                />
                <ResultMetric
                  label="DV01"
                  value={result.dv01}
                  suffix=" 元/BP"
                />
              </div>
              <div className="method-note">
                <CheckCircle2 size={16} />
                <span>{result.methodology}</span>
              </div>
            </div>
          ) : (
            <div className="empty-state calculator-empty">
              <Calculator size={34} />
              <strong>输入参数后开始计算</strong>
              <p>支持固定利率附息债、零息债与三种计息日规则。</p>
            </div>
          )}
        </Panel>
      </div>

      {result ? (
        <div className="two-column">
          <Panel title="收益率冲击" eyebrow="SCENARIO">
            <div className="scenario-grid">
              {Object.entries(result.scenario_prices).map(([label, value]) => (
                <article key={label}>
                  <span>{label}</span>
                  <strong>{formatNumber(value, 5)}</strong>
                </article>
              ))}
            </div>
          </Panel>
          <Panel title="现金流" eyebrow="CASH FLOW">
            <div className="table-wrap compact">
              <table>
                <thead>
                  <tr>
                    <th>日期</th>
                    <th className="num">距今</th>
                    <th className="num">现金流</th>
                    <th className="num">现值</th>
                  </tr>
                </thead>
                <tbody>
                  {result.cash_flows.map((flow) => (
                    <tr key={flow.date}>
                      <td>{flow.date}</td>
                      <td className="num mono">{formatNumber(flow.years, 3)} 年</td>
                      <td className="num mono">{formatNumber(flow.amount, 4)}</td>
                      <td className="num mono">{formatNumber(flow.present_value, 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}

function ResultMetric({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number;
  suffix: string;
}) {
  return (
    <article>
      <span>{label}</span>
      <strong>
        {formatNumber(value, 4)}
        <small>{suffix}</small>
      </strong>
    </article>
  );
}
