// Kept separate from InitialOfficeSetupWizard so App can check for an
// in-progress setup draft without pulling the whole wizard into the
// initial bundle (the wizard page itself is lazy-loaded).
export const SETUP_DRAFT_KEY = 'negotium-initial-setup-draft';

export function hasIncompleteInitialSetupDraft(): boolean {
  try {
    const raw = window.localStorage.getItem(SETUP_DRAFT_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw) as { step?: string };
    return Boolean(parsed.step && parsed.step !== 'admin');
  } catch {
    return false;
  }
}
