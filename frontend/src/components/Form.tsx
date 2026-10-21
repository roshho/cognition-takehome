import { useState } from "react";
import type { FormEvent, ReactNode } from "react";

interface FormProps {
  title?: string;
  submitLabel?: string;
  onSubmit: () => Promise<void>;
  children: ReactNode;
}

/** Shared form wrapper: consistent submit + inline error handling. */
export function Form({ title, submitLabel = "Save", onSubmit, children }: FormProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card form" onSubmit={handleSubmit}>
      {title && <h3>{title}</h3>}
      {children}
      {error && <p className="form-error">{error}</p>}
      <button className="btn primary" type="submit" disabled={busy}>
        {busy ? "Saving…" : submitLabel}
      </button>
    </form>
  );
}

export function FormField({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="form-field">
      <span className="form-label">{label}</span>
      {children}
    </label>
  );
}
