import React, { useState, useEffect, useRef, useCallback } from "react";

// ── Configuração ──────────────────────────────────────────────────────────────
const ANCHOR_ISO       = "2026-05-16T22:00:00-03:00";
const INTERVAL_MIN     = 210;
const REMINDER_MIN     = 5;
const BOSS_DURATION_MIN = 15;

const anchorMs   = new Date(ANCHOR_ISO).getTime();
const intervalMs = INTERVAL_MIN     * 60_000;
const reminderMs = REMINDER_MIN     * 60_000;
const durationMs = BOSS_DURATION_MIN * 60_000;

// ── Lógica pura ───────────────────────────────────────────────────────────────
function getNextBoss(now: number): number {
  const elapsed        = now - anchorMs;
  const intervalsPassed = Math.ceil(elapsed / intervalMs);
  return anchorMs + intervalsPassed * intervalMs;
}

function getReminderTime(bossTime: number): number {
  return bossTime - reminderMs;
}

function formatCountdown(ms: number): string {
  if (ms <= 0) return "00:00";
  const s  = Math.floor(ms / 1000);
  const h  = Math.floor(s / 3600);
  const m  = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (h > 0)
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  return `${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

function generateUpcomingBosses(now: number, qty: number): number[] {
  const list: number[] = [];
  let next = getNextBoss(now);
  for (let i = 0; i < qty; i++) {
    list.push(next);
    next += intervalMs;
  }
  return list;
}

function formatBossTime(ts: number): string {
  return new Date(ts).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatShort(ts: number): string {
  return new Date(ts).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Estilos inline para efeitos que o Tailwind não cobre ──────────────────────
const GLOW_RED    = "0 0 24px 4px rgba(180,0,0,0.7), 0 0 60px 10px rgba(120,0,0,0.4)";
const GLOW_GOLD   = "0 0 12px 2px rgba(200,160,0,0.5)";
const GLOW_PULSE  = "0 0 40px 12px rgba(220,30,30,0.9), 0 0 80px 20px rgba(180,0,0,0.6)";
const BORDER_GOLD = "1px solid rgba(180,140,0,0.6)";

// ── Ornamento de canto ────────────────────────────────────────────────────────
function Corner({ rotate = 0 }: { rotate?: number }) {
  return (
    <svg
      width={32} height={32}
      style={{ transform: `rotate(${rotate}deg)`, flexShrink: 0 }}
      viewBox="0 0 32 32" fill="none"
    >
      <path d="M2 30 L2 2 L30 2" stroke="rgba(180,140,0,0.8)" strokeWidth="2" fill="none" />
      <path d="M2 2 L10 10" stroke="rgba(180,140,0,0.5)" strokeWidth="1" />
      <circle cx="2" cy="2" r="3" fill="rgba(180,140,0,0.9)" />
    </svg>
  );
}

// ── Divisor ornamentado ───────────────────────────────────────────────────────
function Divider() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "8px 0" }}>
      <div style={{ flex: 1, height: 1, background: "linear-gradient(to right, transparent, rgba(180,140,0,0.5))" }} />
      <svg width={16} height={16} viewBox="0 0 16 16">
        <polygon points="8,0 16,8 8,16 0,8" fill="rgba(180,100,0,0.8)" />
      </svg>
      <div style={{ flex: 1, height: 1, background: "linear-gradient(to left, transparent, rgba(180,140,0,0.5))" }} />
    </div>
  );
}

// ── Componente principal ──────────────────────────────────────────────────────
export default function WorldBossReminder() {
  const [now, setNow]               = useState(Date.now);
  const [alertedBoss, setAlertedBoss] = useState<number | null>(null);
  const [notifPerm, setNotifPerm]   = useState<NotificationPermission>("default");
  const [activeBoss, setActiveBoss] = useState(false);
  const audioRef = useRef<AudioContext | null>(null);

  // Tick a cada segundo
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Permissão de notificação
  useEffect(() => {
    if ("Notification" in window) setNotifPerm(Notification.permission);
  }, []);

  const requestNotif = useCallback(async () => {
    if (!("Notification" in window)) return;
    const perm = await Notification.requestPermission();
    setNotifPerm(perm);
  }, []);

  // Beep sintético
  const playBeep = useCallback(() => {
    try {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(110, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(55, ctx.currentTime + 0.5);
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);
      osc.start();
      osc.stop(ctx.currentTime + 0.8);
    } catch (_) {}
  }, []);

  const nextBoss   = getNextBoss(now);
  const msToNext   = nextBoss - now;
  const msToRemind = getReminderTime(nextBoss) - now;
  const upcoming   = generateUpcomingBosses(now, 5);

  const isWarning  = msToNext > 0 && msToNext <= reminderMs;
  const isActive   = msToNext <= 0 && msToNext > -durationMs;

  // Alerta de lembrete
  useEffect(() => {
    if (isWarning && alertedBoss !== nextBoss) {
      setAlertedBoss(nextBoss);
      playBeep();
      if (notifPerm === "granted") {
        new Notification("⚔️ Boss Mundial em 5 minutos!", {
          body: `Aparece às ${formatShort(nextBoss)} — prepare-se!`,
          icon: undefined,
        });
      }
    }
  }, [isWarning, nextBoss, alertedBoss, notifPerm, playBeep]);

  useEffect(() => { setActiveBoss(isActive); }, [isActive]);

  // ── Render ────────────────────────────────────────────────────────────────
  const cardStyle: React.CSSProperties = {
    background: "linear-gradient(160deg, #0d0000 0%, #1a0505 40%, #0d0000 100%)",
    border: BORDER_GOLD,
    boxShadow: isWarning || isActive ? GLOW_PULSE : GLOW_RED,
    borderRadius: 4,
    padding: "24px 20px",
    maxWidth: 420,
    width: "100%",
    position: "relative",
    fontFamily: "'Georgia', serif",
    transition: "box-shadow 0.5s ease",
  };

  const titleStyle: React.CSSProperties = {
    color: "#c8a020",
    fontSize: 22,
    fontWeight: "bold",
    letterSpacing: 3,
    textTransform: "uppercase",
    textShadow: GLOW_GOLD,
    textAlign: "center",
    margin: 0,
  };

  const subtitleStyle: React.CSSProperties = {
    color: "rgba(160,80,40,0.8)",
    fontSize: 12,
    letterSpacing: 5,
    textTransform: "uppercase",
    textAlign: "center",
    marginBottom: 4,
  };

  const countdownStyle: React.CSSProperties = {
    color: isWarning || isActive ? "#ff3020" : "#e8c060",
    fontSize: isWarning || isActive ? 56 : 48,
    fontWeight: "bold",
    textAlign: "center",
    letterSpacing: 4,
    textShadow: isWarning || isActive
      ? "0 0 20px rgba(255,50,0,0.9), 0 0 40px rgba(200,0,0,0.6)"
      : GLOW_GOLD,
    lineHeight: 1,
    transition: "all 0.3s ease",
    fontFamily: "monospace",
  };

  const labelStyle: React.CSSProperties = {
    color: "rgba(180,140,60,0.6)",
    fontSize: 11,
    letterSpacing: 3,
    textTransform: "uppercase",
    textAlign: "center",
  };

  const nextTimeStyle: React.CSSProperties = {
    color: "#c8a020",
    fontSize: 15,
    textAlign: "center",
    letterSpacing: 1,
    textShadow: GLOW_GOLD,
  };

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", padding: 16 }}>
      <div style={cardStyle}>

        {/* Cantos ornamentados */}
        <div style={{ position: "absolute", top: 8, left: 8 }}><Corner rotate={0} /></div>
        <div style={{ position: "absolute", top: 8, right: 8 }}><Corner rotate={90} /></div>
        <div style={{ position: "absolute", bottom: 8, right: 8 }}><Corner rotate={180} /></div>
        <div style={{ position: "absolute", bottom: 8, left: 8 }}><Corner rotate={270} /></div>

        {/* Título */}
        <div style={{ textAlign: "center", marginBottom: 4 }}>
          <p style={subtitleStyle}>⚔ Santuário aguarda... ⚔</p>
          <h1 style={titleStyle}>Boss Mundial</h1>
        </div>

        <Divider />

        {/* Status ativo */}
        {isActive && (
          <div style={{
            background: "rgba(180,0,0,0.25)",
            border: "1px solid rgba(220,30,30,0.6)",
            borderRadius: 3,
            padding: "8px 12px",
            textAlign: "center",
            marginBottom: 12,
            color: "#ff6040",
            fontSize: 14,
            letterSpacing: 2,
            textTransform: "uppercase",
            fontWeight: "bold",
            animation: "pulse 1s infinite",
          }}>
            ⚠ BOSS ATIVO AGORA ⚠
          </div>
        )}

        {/* Alerta 5 min */}
        {isWarning && !isActive && (
          <div style={{
            background: "rgba(140,20,0,0.3)",
            border: "1px solid rgba(200,60,0,0.5)",
            borderRadius: 3,
            padding: "6px 12px",
            textAlign: "center",
            marginBottom: 12,
            color: "#ff8050",
            fontSize: 13,
            letterSpacing: 2,
          }}>
            ⚡ PREPARE-SE — BOSS EM BREVE ⚡
          </div>
        )}

        {/* Countdown */}
        <div style={{ margin: "16px 0 8px" }}>
          <p style={labelStyle}>{isActive ? "Encerra em" : "Próximo boss em"}</p>
          <p style={countdownStyle}>
            {isActive ? formatCountdown(durationMs + (msToNext)) : formatCountdown(msToNext)}
          </p>
          <p style={nextTimeStyle}>{formatBossTime(nextBoss)}</p>
        </div>

        <Divider />

        {/* Próximos 5 bosses */}
        <div style={{ marginTop: 8 }}>
          <p style={{ ...labelStyle, marginBottom: 8 }}>Próximos bosses</p>
          {upcoming.map((ts, i) => (
            <div key={ts} style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "5px 8px",
              marginBottom: 3,
              borderRadius: 2,
              background: i === 0
                ? "rgba(120,40,0,0.3)"
                : "rgba(40,10,10,0.4)",
              border: i === 0
                ? "1px solid rgba(180,80,0,0.4)"
                : "1px solid rgba(80,30,0,0.2)",
            }}>
              <span style={{ color: i === 0 ? "#e09040" : "rgba(160,110,50,0.7)", fontSize: 13 }}>
                {i === 0 ? "▶ " : `${i + 1}. `}{formatBossTime(ts)}
              </span>
              <span style={{ color: "rgba(140,100,40,0.6)", fontSize: 11 }}>
                {i === 0 ? formatCountdown(ts - now) : `+${(i * INTERVAL_MIN / 60).toFixed(1)}h`}
              </span>
            </div>
          ))}
        </div>

        <Divider />

        {/* Notificação */}
        <div style={{ textAlign: "center", marginTop: 8 }}>
          {notifPerm !== "granted" ? (
            <button
              onClick={requestNotif}
              style={{
                background: "linear-gradient(to bottom, #3a1000, #1a0500)",
                border: BORDER_GOLD,
                color: "#c8a020",
                padding: "6px 20px",
                fontSize: 12,
                letterSpacing: 2,
                textTransform: "uppercase",
                cursor: "pointer",
                borderRadius: 2,
                boxShadow: GLOW_GOLD,
              }}
            >
              🔔 Ativar notificações
            </button>
          ) : (
            <p style={{ color: "rgba(100,160,80,0.7)", fontSize: 11, letterSpacing: 2 }}>
              ✓ Notificações ativas
            </p>
          )}
          <p style={{ color: "rgba(100,60,40,0.5)", fontSize: 10, marginTop: 6, letterSpacing: 1 }}>
            Intervalo: {INTERVAL_MIN}min · Aviso: {REMINDER_MIN}min antes · Duração: {BOSS_DURATION_MIN}min
          </p>
        </div>

      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
      `}</style>
    </div>
  );
}
