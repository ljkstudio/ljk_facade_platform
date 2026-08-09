import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AdaptiveMoldParams,
  type SessionState,
} from "../api/client";
import { PinGridViewer } from "../components/PinGridViewer";

const defaultParams: AdaptiveMoldParams = {
  width: 1000,
  length: 1000,
  spacing: 200,
  max_height: 400,
  min_height: 0,
  rod_base_length: 300,
  panel_name: "",
};

export function AdaptiveMoldView() {
  const [session, setSession] = useState<SessionState | null>(null);
  const [params, setParams] = useState<AdaptiveMoldParams>(defaultParams);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const s = await api.getSession();
      setSession(s);
      setParams(s.params);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 3000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const saveParams = async () => {
    setLoading(true);
    try {
      const s = await api.updateParams(params);
      setSession(s);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const requestCompute = async () => {
    setLoading(true);
    try {
      await api.updateParams(params);
      const s = await api.requestCompute();
      setSession(s);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const update = (key: keyof AdaptiveMoldParams, value: string | number) => {
    setParams((p) => ({ ...p, [key]: value }));
  };

  const statusClass =
    session?.status === "synced"
      ? "ok"
      : session?.status === "compute_requested"
        ? "warn"
        : session?.status === "error"
          ? "error"
          : "";

  return (
    <>
      <div className="card">
        <h2>연결 상태</h2>
        <div className="status-bar">
          <span className={`chip ${session?.gh_connected ? "ok" : ""}`}>
            GH {session?.gh_connected ? "연결됨" : "미연결"}
          </span>
          <span className={`chip ${statusClass}`}>
            세션: {session?.status ?? "—"}
          </span>
          {session?.last_sync_at && (
            <span className="chip">
              동기화: {new Date(session.last_sync_at).toLocaleTimeString()}
            </span>
          )}
        </div>
        {error && <p className="error-text">{error}</p>}
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>AdaptiveMold v1 파라미터</h2>
          <div className="field">
            <label>패널 이름</label>
            <input
              value={params.panel_name}
              onChange={(e) => update("panel_name", e.target.value)}
            />
          </div>
          {(
            [
              ["width", "Width (mm)"],
              ["length", "Length (mm)"],
              ["spacing", "Spacing (mm)"],
              ["max_height", "Max stroke (mm)"],
              ["min_height", "Min stroke (mm)"],
              ["rod_base_length", "Rod base length (mm)"],
            ] as const
          ).map(([key, label]) => (
            <div className="field" key={key}>
              <label>{label}</label>
              <input
                type="number"
                value={params[key]}
                onChange={(e) => update(key, Number(e.target.value))}
              />
            </div>
          ))}
          <div className="actions">
            <button className="btn btn-secondary" onClick={saveParams} disabled={loading}>
              파라미터 저장
            </button>
            <button className="btn btn-primary" onClick={requestCompute} disabled={loading}>
              GH 재계산 요청
            </button>
            <button className="btn btn-secondary" onClick={refresh} disabled={loading}>
              새로고침
            </button>
          </div>
          <p style={{ fontSize: "0.82rem", color: "#94a3b8", marginTop: "0.75rem" }}>
            재계산 요청 후 Grasshopper에서 AMv1 Bridge(pull) → AMv1(compute + sync)를
            실행하세요.
          </p>
        </div>

        <div className="card">
          <h2>3D Pin Grid</h2>
          <PinGridViewer
            result={session?.result ?? null}
            maxHeight={params.max_height}
          />
        </div>
      </div>

      {session?.result && (
        <div className="card">
          <h2>결과 리포트</h2>
          {session.result.fabricability && (
            <div className="status-bar" style={{ marginBottom: "0.75rem" }}>
              <span
                className={`chip ${session.result.fabricability.is_fabricable ? "ok" : "error"}`}
              >
                Fabricable: {String(session.result.fabricability.is_fabricable)}
              </span>
              <span className="chip">
                Clamped: {session.result.fabricability.clamped_pin_count}
              </span>
              <span className="chip">
                Extension pins: {session.result.fabricability.out_of_bounds_pin_count}
              </span>
            </div>
          )}
          <pre className="report-pre">{session.result.info}</pre>
        </div>
      )}
    </>
  );
}
