import { useEffect, useRef } from 'react';

/*
 * Login backdrop: drifting, twinkling stardust plus a constellation of agent steps
 * (Trigger -> AI agent -> Decide -> Act / Notify -> Done). Dust particles stream along
 * each connection and make a step glow as they arrive, like a workflow running.
 * Pure canvas, no dependencies. Respects prefers-reduced-motion (draws one still frame).
 */

const STEPS = [
  { id: 'trigger', label: 'Trigger', x: 0.14, y: 0.5 },
  { id: 'agent', label: 'AI agent', x: 0.34, y: 0.36 },
  { id: 'decide', label: 'Decide', x: 0.52, y: 0.56 },
  { id: 'act', label: 'Act', x: 0.72, y: 0.36 },
  { id: 'notify', label: 'Notify', x: 0.72, y: 0.74 },
  { id: 'done', label: 'Done', x: 0.88, y: 0.54 },
];
const LINKS = [
  ['trigger', 'agent'], ['agent', 'decide'], ['decide', 'act'], ['decide', 'notify'], ['act', 'done'], ['notify', 'done'],
];

function brandRgb(shade, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--brand-${shade}`).trim();
  return v ? v.split(/\s+/).join(',') : fallback;
}

export default function StarDustScene() {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext('2d');
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const accent = brandRgb(300, '165,180,252');
    const accentStrong = brandRgb(400, '129,140,248');
    let w = 0;
    let h = 0;
    let raf = 0;
    let stars = [];
    const glow = Object.fromEntries(STEPS.map((s) => [s.id, 0]));
    const dust = [];

    const pos = (id) => {
      const s = STEPS.find((x) => x.id === id);
      return { x: s.x * w, y: s.y * h };
    };

    // Gentle curve between two steps (control point lifted for an organic arc).
    const curve = (a, b, t) => {
      const p0 = pos(a);
      const p2 = pos(b);
      const c = { x: (p0.x + p2.x) / 2, y: (p0.y + p2.y) / 2 - h * 0.06 };
      const u = 1 - t;
      return { x: u * u * p0.x + 2 * u * t * c.x + t * t * p2.x, y: u * u * p0.y + 2 * u * t * c.y + t * t * p2.y };
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.round((w * h) / 4500);
      stars = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.3 + 0.2,
        tw: Math.random() * Math.PI * 2,
        vx: (Math.random() - 0.5) * 0.06,
        vy: (Math.random() - 0.5) * 0.06,
      }));
    };

    const spawn = () => {
      const [a, b] = LINKS[Math.floor(Math.random() * LINKS.length)];
      dust.push({ a, b, t: 0, speed: 0.004 + Math.random() * 0.004, size: 1 + Math.random() * 1.6 });
    };

    const frame = (time) => {
      ctx.clearRect(0, 0, w, h);

      // Stardust field
      for (const s of stars) {
        if (!reduce) {
          s.x = (s.x + s.vx + w) % w;
          s.y = (s.y + s.vy + h) % h;
        }
        const alpha = 0.35 + 0.35 * Math.sin(time / 900 + s.tw);
        ctx.fillStyle = `rgba(255,255,255,${alpha.toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }

      // Constellation links
      ctx.lineWidth = 1;
      for (const [a, b] of LINKS) {
        ctx.strokeStyle = `rgba(${accent},0.22)`;
        ctx.beginPath();
        for (let i = 0; i <= 24; i++) {
          const p = curve(a, b, i / 24);
          if (i === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
      }

      // Dust flowing along the links (each with a short fading trail)
      if (!reduce && Math.random() < 0.18) spawn();
      for (let i = dust.length - 1; i >= 0; i--) {
        const d = dust[i];
        d.t += reduce ? 0 : d.speed;
        if (d.t >= 1) {
          glow[d.b] = 1;
          dust.splice(i, 1);
          continue;
        }
        for (let k = 0; k < 6; k++) {
          const tt = Math.max(0, d.t - k * 0.012);
          const p = curve(d.a, d.b, tt);
          ctx.fillStyle = `rgba(${k === 0 ? '255,255,255' : accent},${(0.9 - k * 0.14).toFixed(2)})`;
          ctx.beginPath();
          ctx.arc(p.x, p.y, Math.max(0.3, d.size - k * 0.2), 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Agent steps
      ctx.font = '500 13px ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      for (const s of STEPS) {
        const p = pos(s.id);
        const g = glow[s.id];
        glow[s.id] = Math.max(0, g - 0.02);
        const radius = 9 + g * 4;
        const halo = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, 34 + g * 18);
        halo.addColorStop(0, `rgba(${accentStrong},${(0.35 + g * 0.4).toFixed(2)})`);
        halo.addColorStop(1, `rgba(${accentStrong},0)`);
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 34 + g * 18, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = `rgba(${accentStrong},1)`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius * 0.45, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = 'rgba(255,255,255,0.85)';
        ctx.fillText(s.label, p.x, p.y + 32);
      }

      if (!reduce) raf = requestAnimationFrame(frame);
    };

    resize();
    if (reduce) {
      for (let i = 0; i < 12; i++) dust.push({ ...LINKS.map(([a, b]) => ({ a, b }))[i % LINKS.length], t: Math.random(), speed: 0, size: 1.4 });
    }
    raf = requestAnimationFrame(frame);
    const ro = new ResizeObserver(() => {
      resize();
      if (reduce) requestAnimationFrame(frame);
    });
    ro.observe(canvas);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return <canvas ref={ref} className="absolute inset-0 h-full w-full" aria-hidden="true" />;
}
