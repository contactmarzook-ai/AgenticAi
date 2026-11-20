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

export const CATEGORY_STYLE = {
  AI: { text: 'text-violet-700', bg: 'bg-violet-50', border: 'border-violet-400' },
  Apps: { text: 'text-sky-700', bg: 'bg-sky-50', border: 'border-sky-400' },
  Data: { text: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-400' },
  Flow: { text: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-400' },
  Start: { text: 'text-green-700', bg: 'bg-green-50', border: 'border-green-500' },
  Finish: { text: 'text-gray-800', bg: 'bg-gray-100', border: 'border-gray-700' },
};
