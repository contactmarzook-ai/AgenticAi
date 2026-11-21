import { useEffect, useRef } from 'react';

/*
 * Login backdrop: a slowly rotating spiral galaxy, drawn on a 2D canvas (no dependencies).
 *
 * How it is built
 *  - Stars follow the density-wave model: every star moves on its own ellipse around the core,
 *    and the ellipses turn a little more with every step outwards (a logarithmic twist,
 *    phi = ln(1 + a/a0) / tan(pitch)). Where neighbouring ellipses crowd together two
 *    logarithmic spiral arms appear. Inner stars orbit faster than outer ones (differential
 *    rotation) and the arm pattern itself turns slowly, so the arms never wind up.
 *  - Core, disk haze, nebula clouds and dust lanes are painted once into a separate "glow
 *    layer" canvas (in the galaxy plane). It is tilted and turned with the arm pattern by a CSS
 *    transform, so the GPU compositor moves it and the 2D canvas never redraws it. Clouds are
 *    placed where the stars crowd, so they trace the arms.
 *  - Bright stars, the travelling "agent" stars and the twinkling field stars use pre-rendered
 *    glow sprites instead of shadowBlur. Faint stars are batched fillRects grouped by colour.
 *  - A parallax starfield (three depths), an occasional shooting star, a slight perspective tilt
 *    and a small mouse parallax add depth.
 * Performance: particle counts scale with the canvas area, requestAnimationFrame only while the
 * tab is visible, stopped on unmount. prefers-reduced-motion draws one still frame.
 */

const TAU = Math.PI * 2;
const PITCH = (22 * Math.PI) / 180; // arm pitch angle
const TWIST = 1 / Math.tan(PITCH);
const A0 = 0.08; // where the logarithmic twist starts
const TILT = 0.5; // perspective: the disk is seen at ~60 degrees
const VIEW = -0.42; // on-screen rotation of the disk's long axis
const PATTERN_SPEED = 0.012; // rad/s, the arms turning as a whole
const ALPHA_LEVELS = 6;

// Colours come from the theme tokens in src/theme.css ("R G B" triplets).
function themeRgb(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
  return v ? v.split(/\s+/).map(Number) : fallback;
}

// Seeded random numbers: the galaxy looks the same on every visit and after a resize.
function mulberry32(seed) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const gauss = (rand) => Math.sqrt(-2 * Math.log(rand() + 1e-9)) * Math.cos(TAU * rand());

const ellipseRatio = (a) => (a < 0.1 ? 1 - (a / 0.1) * 0.42 : a < 0.95 ? 0.58 + ((a - 0.1) / 0.85) * 0.14 : 0.72 + Math.min(0.2, (a - 0.95) * 0.8));
const orientation = (a) => TWIST * Math.log(1 + a / A0);
const angularSpeed = (a) => 0.05 / (a + 0.1);
// Stars linger near the ends of their ellipse (like real orbits slowing near apocentre). Those
// ends lie on r = a, angle = phi(a): a logarithmic spiral, so the two arms stand out clearly.
const LINGER = 0.62;
const orbitAngle = (m) => m - (LINGER / 2) * Math.sin(2 * m);

// A soft round glow, pre-rendered once per colour.
function makeSprite([r, g, b], size = 64, core = 0.55) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const x = c.getContext('2d');
  const grad = x.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, `rgba(255,255,255,${core})`);
  grad.addColorStop(0.12, `rgba(${r},${g},${b},0.55)`);
  grad.addColorStop(0.4, `rgba(${r},${g},${b},0.12)`);
  grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
  x.fillStyle = grad;
  x.fillRect(0, 0, size, size);
  return c;
}

export default function StarDustScene() {
  const ref = useRef(null);
  const glowRef = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    const glowCanvas = glowRef.current;
    const ctx = canvas.getContext('2d');
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    const brand300 = themeRgb('brand-300', [127, 174, 214]);
    const brand500 = themeRgb('brand-500', [52, 119, 181]);
    const navy500 = themeRgb('navy-500', [47, 84, 128]);
    const accent = themeRgb('accent-500', [242, 140, 40]);

    // Star colour temperatures: warm core -> white -> blue arms, a few pink-orange star-forming knots.
    const STAR_COLORS = [
      [255, 214, 170], // 0 warm (core)
      [255, 238, 214], // 1 warm white
      [236, 242, 255], // 2 white
      [196, 216, 255], // 3 blue-white
      [brand300[0], brand300[1] + 10, Math.min(255, brand300[2] + 30)], // 4 brand blue
      [255, 176, 130], // 5 star-forming knot
    ];
    const starStyles = [];
    for (const [r, g, b] of STAR_COLORS) for (let l = 0; l < ALPHA_LEVELS; l++) starStyles.push(`rgba(${r},${g},${b},${(0.22 + (l / (ALPHA_LEVELS - 1)) * 0.73).toFixed(2)})`);
    const sprites = STAR_COLORS.map((c) => makeSprite(c));
    const agentSprite = makeSprite(brand300, 64, 0.95);
    const agentSpriteWarm = makeSprite(accent, 64, 0.95);

    let w = 0;
    let h = 0;
    let dpr = 1;
    let cx = 0;
    let cy = 0;
    let R = 1;
    let N = 0;
    let stars = null; // typed arrays, sorted by draw style
    let bright = []; // indices drawn with a glow sprite
    let agents = [];
    let field = [];
    let glowExtent = 1; // galaxy units covered by half the glow layer
    let shooting = null;
    let nextShooting = 4;
    let t = reduce ? 42 : 0;
    let last = 0;
    let raf = 0;
    let running = false;
    const mouse = { x: 0, y: 0, tx: 0, ty: 0 };

    const build = () => {
      const rand = mulberry32(20251121);
      N = Math.round(Math.min(5000, Math.max(1500, (w * h) / 280)));
      const a = new Float32Array(N);
      const b = new Float32Array(N);
      const cphi = new Float32Array(N);
      const sphi = new Float32Array(N);
      const th0 = new Float32Array(N);
      const om = new Float32Array(N);
      const jx = new Float32Array(N);
      const jy = new Float32Array(N);
      const size = new Float32Array(N);
      const style = new Uint8Array(N);
      const color = new Uint8Array(N);
      const raw = [];
      for (let i = 0; i < N; i++) {
        let ai;
        const bulge = rand() < 0.1;
        if (bulge) ai = Math.abs(gauss(rand)) * 0.07 + 0.005;
        else {
          // exponential disk, scale length 0.45, truncated at 1.12
          const k = 1 / 0.45;
          ai = 0.04 + -Math.log(1 - rand() * (1 - Math.exp(-k * 1.08))) / k;
        }
        const phi = orientation(ai);
        a[i] = ai;
        b[i] = ai * ellipseRatio(ai);
        cphi[i] = Math.cos(phi);
        sphi[i] = Math.sin(phi);
        th0[i] = rand() * TAU;
        om[i] = angularSpeed(ai);
        const spread = 0.005 + ai * 0.02;
        jx[i] = gauss(rand) * spread;
        jy[i] = gauss(rand) * spread;
        const roll = rand();
        let col;
        if (ai < 0.1) col = roll < 0.7 ? 0 : 1;
        else if (ai < 0.3) col = roll < 0.25 ? 1 : roll < 0.75 ? 2 : 3;
        else col = roll < 0.03 ? 5 : roll < 0.3 ? 2 : roll < 0.7 ? 3 : 4;
        color[i] = col;
        const lum = Math.min(1, 0.3 + rand() * 0.6 + (ai < 0.15 ? 0.2 : 0) - ai * 0.12);
        const level = Math.max(0, Math.min(ALPHA_LEVELS - 1, Math.round(lum * (ALPHA_LEVELS - 1))));
        style[i] = col * ALPHA_LEVELS + level;
        size[i] = 0.8 + rand() * 0.9 + (lum > 0.85 ? 0.4 : 0);
        raw.push({ i, bright: rand() < 0.028 && ai > 0.06 });
      }
      // Sort by style so fillStyle changes only a few dozen times per frame.
      raw.sort((p, q) => style[p.i] - style[q.i]);
      const perm = raw.map((p) => p.i);
      const pick = (arr, Ctor) => {
        const out = new Ctor(N);
        for (let k = 0; k < N; k++) out[k] = arr[perm[k]];
        return out;
      };
      stars = { a: pick(a, Float32Array), b: pick(b, Float32Array), cphi: pick(cphi, Float32Array), sphi: pick(sphi, Float32Array), th0: pick(th0, Float32Array), om: pick(om, Float32Array), jx: pick(jx, Float32Array), jy: pick(jy, Float32Array), size: pick(size, Float32Array), style: pick(style, Uint8Array), color: pick(color, Uint8Array) };
      bright = [];
      raw.forEach((p, k) => p.bright && bright.push(k));

      // "Agents": a few brighter stars travelling along the arms; they link briefly when close.
      agents = [0.34, 0.42, 0.5, 0.58, 0.66].map((ai, k) => ({
        a: ai,
        b: ai * ellipseRatio(ai),
        phi: orientation(ai),
        th0: rand() * TAU,
        om: angularSpeed(ai) * (1.15 + k * 0.08),
        warm: k === 2,
      }));

      // Background starfield in three parallax depths.
      const fieldCount = Math.round(Math.min(700, Math.max(160, (w * h) / 2600)));
      field = [];
      for (let i = 0; i < fieldCount; i++) {
        const depth = i % 7 === 0 ? 2 : i % 3 === 0 ? 1 : 0;
        const temp = rand();
        field.push({
          x: rand(),
          y: rand(),
          depth,
          size: depth === 2 ? 1.2 + rand() * 1.1 : depth === 1 ? 0.8 + rand() * 0.6 : 0.5 + rand() * 0.5,
          color: temp < 0.18 ? 1 : temp < 0.55 ? 2 : temp < 0.85 ? 3 : 4,
          base: 0.25 + rand() * (depth === 2 ? 0.6 : 0.45),
          speed: 0.6 + rand() * 2.2,
          phase: rand() * TAU,
        });
      }
      field.sort((p, q) => p.color - q.color);

      buildGlowLayer(rand);
    };

    // Core, disk haze, nebula clouds and dust lanes, in galaxy-plane coordinates (untilted).
    const buildGlowLayer = (rand) => {
      glowExtent = 1.25;
      const S = Math.min(1024, Math.round(2 * glowExtent * R)); // soft content: 1 px per CSS px is plenty
      const span = 2 * glowExtent * R;
      const c = glowCanvas;
      c.width = c.height = S;
      c.style.width = c.style.height = `${span}px`;
      const g = c.getContext('2d');
      const k = S / (2 * glowExtent); // px per galaxy unit
      const mid = S / 2;

      // Faint disk haze.
      let grad = g.createRadialGradient(mid, mid, 0, mid, mid, k * 1.15);
      grad.addColorStop(0, `rgba(${brand500},0.22)`);
      grad.addColorStop(0.45, `rgba(${navy500},0.12)`);
      grad.addColorStop(1, `rgba(${navy500},0)`);
      g.fillStyle = grad;
      g.fillRect(0, 0, S, S);

      // Clouds where stars crowd (sampled from the star orbits at the pattern's rest frame).
      g.globalCompositeOperation = 'lighter';
      const cloud = (ai, th, jxv, jyv) => {
        const x = ai * Math.cos(th) + jxv;
        const y = ai * ellipseRatio(ai) * Math.sin(th) + jyv;
        const phi = orientation(ai);
        return [mid + k * (x * Math.cos(phi) - y * Math.sin(phi)), mid + k * (x * Math.sin(phi) + y * Math.cos(phi))];
      };
      const violet = [92, 84, 178];
      const tints = [brand500, brand500, brand300, violet, violet, accent];
      const clouds = Math.round(220 + R / 3);
      for (let i = 0; i < clouds; i++) {
        const ai = 0.12 + Math.pow(rand(), 1.3) * 0.85;
        const [x, y] = cloud(ai, orbitAngle(rand() * TAU), gauss(rand) * 0.02, gauss(rand) * 0.02);
        const tint = tints[Math.floor(rand() * tints.length)];
        const isAccent = tint === accent;
        const rad = k * (isAccent ? 0.02 + rand() * 0.025 : 0.04 + rand() * 0.08);
        const alpha = isAccent ? 0.07 + rand() * 0.07 : 0.05 + rand() * 0.07;
        grad = g.createRadialGradient(x, y, 0, x, y, rad);
        grad.addColorStop(0, `rgba(${tint},${alpha})`);
        grad.addColorStop(1, `rgba(${tint},0)`);
        g.fillStyle = grad;
        g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
      }

      // Dust lanes: soft erasers along the inner edge of the arms.
      g.globalCompositeOperation = 'destination-out';
      for (let i = 0; i < 110; i++) {
        const ai = 0.14 + rand() * 0.7;
        const [x, y] = cloud(ai, orbitAngle(rand() * TAU), -0.03 * ai, gauss(rand) * 0.015);
        const rad = k * (0.03 + rand() * 0.05);
        grad = g.createRadialGradient(x, y, 0, x, y, rad);
        grad.addColorStop(0, `rgba(0,0,0,${0.28 + rand() * 0.25})`);
        grad.addColorStop(1, 'rgba(0,0,0,0)');
        g.fillStyle = grad;
        g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
      }

      // Glowing core: warm white -> orange -> brand blue.
      g.globalCompositeOperation = 'lighter';
      grad = g.createRadialGradient(mid, mid, 0, mid, mid, k * 0.42);
      grad.addColorStop(0, 'rgba(255,250,240,0.95)');
      grad.addColorStop(0.07, 'rgba(255,232,196,0.85)');
      grad.addColorStop(0.2, `rgba(${accent},0.32)`);
      grad.addColorStop(0.45, `rgba(${brand500},0.16)`);
      grad.addColorStop(1, `rgba(${brand500},0)`);
      g.fillStyle = grad;
      g.fillRect(0, 0, S, S);
    };

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      w = Math.max(1, rect.width);
      h = Math.max(1, rect.height);
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      const wide = w >= 1024;
      cx = wide ? w * 0.4 : w * 0.5;
      cy = wide ? h * 0.5 : h * 0.16; // phones: above the sign-in card
      R = wide ? Math.min(w * 0.42, h * 0.85) : Math.min(w * 0.75, h * 0.42);
      build();
    };

    const project = (gx, gy, ox, oy) => {
      const y1 = gy * TILT;
      return [cx + ox + R * (gx * Math.cos(VIEW) - y1 * Math.sin(VIEW)), cy + oy + R * (gx * Math.sin(VIEW) + y1 * Math.cos(VIEW))];
    };

    const draw = () => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
      ctx.clearRect(0, 0, w, h);
      mouse.x += (mouse.tx - mouse.x) * 0.04;
      mouse.y += (mouse.ty - mouse.y) * 0.04;

      // Background starfield (far stars move least).
      ctx.globalCompositeOperation = 'lighter';
      const shift = [4, 9, 16];
      let currentColor = -1;
      for (const s of field) {
        if (s.color !== currentColor) {
          currentColor = s.color;
          const [r, g, b] = STAR_COLORS[s.color];
          ctx.fillStyle = `rgb(${r},${g},${b})`;
        }
        const tw = reduce ? 0.8 : 0.6 + 0.4 * Math.sin(t * s.speed + s.phase);
        const x = s.x * w - mouse.x * shift[s.depth];
        const y = s.y * h - mouse.y * shift[s.depth];
        ctx.globalAlpha = s.base * tw;
        if (s.depth === 2) {
          const sz = s.size * 7;
          ctx.drawImage(sprites[s.color], x - sz / 2, y - sz / 2, sz, sz);
        } else ctx.fillRect(x, y, s.size, s.size);
      }
      ctx.globalAlpha = 1;

      const ox = -mouse.x * 8;
      const oy = -mouse.y * 8;
      const G = t * PATTERN_SPEED;
      const cosG = Math.cos(G);
      const sinG = Math.sin(G);

      // Glow layer (haze, clouds, dust, core): tilted and turned with the arm pattern by CSS.
      const span = 2 * glowExtent * R;
      glowCanvas.style.transform = `translate(${(cx + ox - span / 2).toFixed(2)}px, ${(cy + oy - span / 2).toFixed(2)}px) rotate(${VIEW}rad) scale(1, ${TILT}) rotate(${G.toFixed(5)}rad)`;

      // Disk stars, batched by style.
      ctx.globalCompositeOperation = 'lighter';
      const { a, b, cphi, sphi, th0, om, jx, jy, size, style, color } = stars;
      const cv = Math.cos(VIEW);
      const sv = Math.sin(VIEW);
      const px = new Float32Array(2); // scratch, avoids allocations per star
      let currentStyle = -1;
      const pos = (k) => {
        const th = orbitAngle(th0[k] + om[k] * t);
        const xe = a[k] * Math.cos(th) + jx[k];
        const ye = b[k] * Math.sin(th) + jy[k];
        const c = cphi[k] * cosG - sphi[k] * sinG;
        const s = sphi[k] * cosG + cphi[k] * sinG;
        const gx = xe * c - ye * s;
        const gy = (xe * s + ye * c) * TILT;
        px[0] = cx + ox + R * (gx * cv - gy * sv);
        px[1] = cy + oy + R * (gx * sv + gy * cv);
      };
      for (let k = 0; k < N; k++) {
        if (style[k] !== currentStyle) {
          currentStyle = style[k];
          ctx.fillStyle = starStyles[currentStyle];
        }
        pos(k);
        const sz = size[k];
        ctx.fillRect(px[0] - sz / 2, px[1] - sz / 2, sz, sz);
      }
      // A few bright stars with a soft glow.
      ctx.globalAlpha = 0.85;
      for (const k of bright) {
        pos(k);
        const sz = 7 + size[k] * 4;
        ctx.drawImage(sprites[color[k]], px[0] - sz / 2, px[1] - sz / 2, sz, sz);
      }
      ctx.globalAlpha = 1;

      // Agent stars: travel along the arms and link briefly with a thin line when close.
      const ap = agents.map((ag) => {
        const th = orbitAngle(ag.th0 + ag.om * t);
        const xe = ag.a * Math.cos(th);
        const ye = ag.b * Math.sin(th);
        const phi = ag.phi + G;
        return project(xe * Math.cos(phi) - ye * Math.sin(phi), xe * Math.sin(phi) + ye * Math.cos(phi), ox, oy);
      });
      const linkDist = R * 0.32;
      ctx.lineWidth = 0.8;
      for (let i = 0; i < ap.length; i++) {
        for (let j = i + 1; j < ap.length; j++) {
          const d = Math.hypot(ap[i][0] - ap[j][0], ap[i][1] - ap[j][1]);
          if (d > linkDist) continue;
          const strength = Math.pow(1 - d / linkDist, 1.5);
          ctx.strokeStyle = `rgba(${brand300},${(strength * 0.55).toFixed(3)})`;
          ctx.beginPath();
          ctx.moveTo(ap[i][0], ap[i][1]);
          ctx.lineTo(ap[j][0], ap[j][1]);
          ctx.stroke();
        }
      }
      ap.forEach(([x, y], i) => {
        const pulse = reduce ? 1 : 0.85 + 0.15 * Math.sin(t * 1.6 + i * 1.3);
        const sz = 16 * pulse;
        ctx.drawImage(agents[i].warm ? agentSpriteWarm : agentSprite, x - sz / 2, y - sz / 2, sz, sz);
        ctx.fillStyle = 'rgba(255,255,255,0.95)';
        ctx.fillRect(x - 0.9, y - 0.9, 1.8, 1.8);
      });

      // Occasional shooting star.
      if (shooting) {
        const sh = shooting;
        const p = sh.age / sh.life;
        const fade = Math.sin(Math.PI * Math.min(1, p));
        const hx = sh.x + sh.vx * sh.age;
        const hy = sh.y + sh.vy * sh.age;
        const len = sh.len * Math.min(1, p * 3);
        const norm = Math.hypot(sh.vx, sh.vy);
        const tx = hx - (sh.vx / norm) * len;
        const ty = hy - (sh.vy / norm) * len;
        const grad = ctx.createLinearGradient(hx, hy, tx, ty);
        grad.addColorStop(0, `rgba(255,255,255,${0.9 * fade})`);
        grad.addColorStop(0.3, `rgba(${brand300},${0.4 * fade})`);
        grad.addColorStop(1, `rgba(${brand300},0)`);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.3;
        ctx.beginPath();
        ctx.moveTo(hx, hy);
        ctx.lineTo(tx, ty);
        ctx.stroke();
      }
      ctx.globalCompositeOperation = 'source-over';
    };

    const step = (dt) => {
      t += dt;
      nextShooting -= dt;
      if (shooting) {
        shooting.age += dt;
        if (shooting.age > shooting.life) shooting = null;
      } else if (nextShooting <= 0) {
        const fromLeft = Math.random() < 0.5;
        const speed = 700 + Math.random() * 400;
        const ang = (fromLeft ? 0.35 : Math.PI - 0.35) + (Math.random() - 0.5) * 0.3;
        shooting = { x: w * (fromLeft ? Math.random() * 0.5 : 0.5 + Math.random() * 0.5), y: h * Math.random() * 0.35, vx: Math.cos(ang) * speed, vy: Math.sin(ang) * speed, age: 0, life: 0.7 + Math.random() * 0.4, len: 120 + Math.random() * 90 };
        nextShooting = 5 + Math.random() * 7;
      }
    };

    const frame = (now) => {
      if (!running) return;
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
      last = now;
      step(dt);
      draw();
      raf = requestAnimationFrame(frame);
    };
    const start = () => {
      if (reduce || running || document.hidden) return;
      running = true;
      last = 0;
      raf = requestAnimationFrame(frame);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };
    const onVisibility = () => (document.hidden ? stop() : start());
    const onPointer = (e) => {
      if (reduce) return;
      mouse.tx = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.ty = (e.clientY / window.innerHeight) * 2 - 1;
    };

    resize();
    draw();
    start();
    const ro = new ResizeObserver(() => {
      resize();
      draw();
    });
    ro.observe(canvas);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pointermove', onPointer, { passive: true });
    return () => {
      stop();
      ro.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pointermove', onPointer);
    };
  }, []);

  return (
    <>
      <canvas ref={glowRef} className="pointer-events-none absolute left-0 top-0 origin-center will-change-transform" aria-hidden="true" />
      <canvas ref={ref} className="absolute inset-0 h-full w-full" aria-hidden="true" />
    </>
  );
}
