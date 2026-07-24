import { ReactNode } from 'react';

// Shared CTA row: keeps buttons content-sized instead of stretching to the
// full width of grid containers like .memory-form.
export default function FormActions({ children }: { children: ReactNode }) {
  return <div className="form-actions">{children}</div>;
}
