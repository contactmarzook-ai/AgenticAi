import { create } from 'zustand';

/** Tracks unsaved work so navigation can ask before throwing it away. */
export const useUnsaved = create((set) => ({
  dirty: false,
  setDirty: (dirty) => set({ dirty }),
}));

export function confirmLeave() {
  return !useUnsaved.getState().dirty || window.confirm('You have unsaved changes. Leave without saving?');
}
