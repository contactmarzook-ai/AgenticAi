import {
  AlignLeft, Bot, Braces, Calculator, Calendar, FilePen, FileText, Flag, GitBranch, Globe, Languages, ListPlus, Mail,
  MessageCircle, MessageSquare, OctagonX, Play, ScanText, Sparkles, Split, Tags, Timer, Type, Zap,
} from 'lucide-react';

// Maps icon names used by the backend node catalog to components.
const ICONS = {
  sparkles: Sparkles, 'align-left': AlignLeft, tags: Tags, 'scan-text': ScanText, languages: Languages, bot: Bot,
  'list-plus': ListPlus, 'file-text': FileText, braces: Braces, calculator: Calculator, calendar: Calendar, type: Type,
  'file-pen': FilePen, globe: Globe, mail: Mail, 'message-square': MessageSquare, 'message-circle': MessageCircle,
  timer: Timer, 'octagon-x': OctagonX, play: Play, flag: Flag, 'git-branch': GitBranch, split: Split,
};

export function iconFor(name) {
  return ICONS[name] || Zap;
}

// Step categories on the builder canvas. Brand-palette based, but kept visually distinct;
// AI steps carry the orange accent (dark orange text on a pale tint for contrast).
export const CATEGORY_STYLE = {
  AI: { text: 'text-accent-700', bg: 'bg-accent-50', border: 'border-accent' },
  Apps: { text: 'text-brand-700', bg: 'bg-brand-50', border: 'border-brand-500' },
  Data: { text: 'text-teal-700', bg: 'bg-teal-50', border: 'border-teal-500' },
  Flow: { text: 'text-slate-700', bg: 'bg-slate-100', border: 'border-slate-500' },
  Start: { text: 'text-green-700', bg: 'bg-green-50', border: 'border-green-600' },
  Finish: { text: 'text-navy', bg: 'bg-navy-50', border: 'border-navy' },
};
