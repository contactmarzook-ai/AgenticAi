import { useState } from 'react';
import { Field, Input, Select } from '../../lib/ui';

const DAYS = [['1', 'Mon'], ['2', 'Tue'], ['3', 'Wed'], ['4', 'Thu'], ['5', 'Fri'], ['6', 'Sat'], ['0', 'Sun']];

/** Turn a plain-language choice into a cron expression. */
export function toCron(s) {
  const [h, m] = (s.time || '09:00').split(':').map((x) => parseInt(x, 10) || 0);
  switch (s.mode) {
    case 'minutes': return `*/${Math.max(1, Math.min(59, Number(s.every) || 15))} * * * *`;
    case 'hourly': return `${m} * * * *`;
    case 'daily': return `${m} ${h} * * *`;
    case 'weekdays': return `${m} ${h} * * 1-5`;
    case 'weekly': return `${m} ${h} * * ${(s.days?.length ? s.days : ['1']).join(',')}`;
    case 'monthly': return `${m} ${h} ${Math.max(1, Math.min(28, Number(s.day) || 1))} * *`;
    default: return s.cron || '0 9 * * *';
  }
}

/** Best-effort reverse: recognise crons this picker produces, otherwise "custom". */
export function fromCron(cron) {
  const p = (cron || '').trim().split(/\s+/);
  if (p.length !== 5) return { mode: 'daily', time: '09:00' };
  const [min, hour, dom, mon, dow] = p;
  const time = /^\d+$/.test(hour) && /^\d+$/.test(min) ? `${hour.padStart(2, '0')}:${min.padStart(2, '0')}` : '09:00';
  if (/^\*\/\d+$/.test(min) && hour === '*' && dom === '*' && mon === '*' && dow === '*') return { mode: 'minutes', every: Number(min.slice(2)) };
  if (/^\d+$/.test(min) && hour === '*' && dom === '*' && dow === '*') return { mode: 'hourly', time: `00:${min.padStart(2, '0')}` };
  if (/^\d+$/.test(hour) && dom === '*' && mon === '*') {
    if (dow === '*') return { mode: 'daily', time };
    if (dow === '1-5') return { mode: 'weekdays', time };
    if (/^[0-6](,[0-6])*$/.test(dow)) return { mode: 'weekly', time, days: dow.split(',') };
  }
  if (/^\d+$/.test(hour) && /^\d+$/.test(dom) && mon === '*' && dow === '*') return { mode: 'monthly', time, day: Number(dom) };
  return { mode: 'custom', cron };
}

export function describeCron(cron) {
  const s = fromCron(cron);
  const days = (s.days || []).map((d) => DAYS.find(([v]) => v === d)?.[1]).join(', ');
  return {
    minutes: `Every ${s.every} minutes`,
    hourly: `Every hour at :${(s.time || '00:00').split(':')[1]}`,
    daily: `Every day at ${s.time}`,
    weekdays: `Weekdays at ${s.time}`,
    weekly: `Every ${days} at ${s.time}`,
    monthly: `Monthly on day ${s.day} at ${s.time}`,
    custom: `Custom: ${cron}`,
  }[s.mode];
}

export default function SchedulePicker({ cron, onChange }) {
  const [s, setS] = useState(() => fromCron(cron));
  const update = (patch) => {
    const next = { ...s, ...patch };
    setS(next);
    onChange(toCron(next));
  };
  return (
    <div className="space-y-2">
      <div className="grid gap-2 md:grid-cols-2">
        <Field label="Repeat">
          <Select value={s.mode} onChange={(e) => update({ mode: e.target.value, cron: cron })}>
            <option value="minutes">Every few minutes</option>
            <option value="hourly">Every hour</option>
            <option value="daily">Every day</option>
            <option value="weekdays">Every weekday (Mon–Fri)</option>
            <option value="weekly">On chosen days</option>
            <option value="monthly">Once a month</option>
            <option value="custom">Custom (cron expression)</option>
          </Select>
        </Field>
        {s.mode === 'minutes' && (
          <Field label="Every (minutes)">
            <Select value={s.every || 15} onChange={(e) => update({ every: Number(e.target.value) })}>
              {[5, 10, 15, 30].map((n) => <option key={n} value={n}>{n}</option>)}
            </Select>
          </Field>
        )}
        {s.mode === 'hourly' && (
          <Field label="At minute">
            <Input type="number" min="0" max="59" value={Number((s.time || '00:00').split(':')[1])} onChange={(e) => update({ time: `00:${String(e.target.value).padStart(2, '0')}` })} />
          </Field>
        )}
        {['daily', 'weekdays', 'weekly', 'monthly'].includes(s.mode) && (
          <Field label="At time">
            <Input type="time" value={s.time || '09:00'} onChange={(e) => update({ time: e.target.value })} />
          </Field>
        )}
        {s.mode === 'monthly' && (
          <Field label="Day of month (1–28)">
            <Input type="number" min="1" max="28" value={s.day || 1} onChange={(e) => update({ day: Number(e.target.value) })} />
          </Field>
        )}
        {s.mode === 'custom' && (
          <Field label="Cron expression" hint="minute hour day month weekday">
            <Input className="font-mono" value={s.cron || cron || ''} onChange={(e) => { setS({ ...s, cron: e.target.value }); onChange(e.target.value); }} />
          </Field>
        )}
      </div>
      {s.mode === 'weekly' && (
        <div className="flex flex-wrap gap-1">
          {DAYS.map(([v, label]) => {
            const on = (s.days || ['1']).includes(v);
            return (
              <button key={v} type="button" onClick={() => {
                  const days = s.days || ['1'];
                  if (on && days.length === 1) return; // at least one day stays selected
                  update({ days: on ? days.filter((d) => d !== v) : [...days, v] });
                }}
                className={`rounded-full border px-2.5 py-1 text-xs ${on ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'text-gray-600'}`}>
                {label}
              </button>
            );
          })}
        </div>
      )}
      <p className="text-xs text-gray-500">{describeCron(toCron(s))}</p>
    </div>
  );
}
