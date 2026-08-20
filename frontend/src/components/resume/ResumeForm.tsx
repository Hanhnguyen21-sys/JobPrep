"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

interface ResumeFormProps {
  onSubmit: (text: string, targetPosition: string) => void;
  loading: boolean;
  error: string | null;
}

// Doesn't call useResume() itself — the hook lives in app/resume/page.tsx
// so this form and ExtractedSkillsList share one source of truth for
// loading/error/skills instead of each holding their own copy.
export function ResumeForm({ onSubmit, loading, error }: ResumeFormProps) {
  const [targetPosition, setTargetPosition] = useState("");
  const [text, setText] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim() || !targetPosition.trim()) return;
    onSubmit(text, targetPosition.trim());
  }

  const canSubmit = !loading && !!text.trim() && !!targetPosition.trim();

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label
          htmlFor="target-position"
          className="mb-1 block text-sm font-medium"
        >
          What position are you looking for?
        </label>
        <Input
          id="target-position"
          value={targetPosition}
          onChange={(e) => setTargetPosition(e.target.value)}
          placeholder="e.g. Software Engineer"
        />
      </div>

      <div>
        <label
          htmlFor="resume-text"
          className="mb-1 block text-sm font-medium"
        >
          Paste your resume text
        </label>
        <textarea
          id="resume-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={14}
          placeholder="Paste the text of your resume here..."
          className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-black dark:border-zinc-700 dark:bg-zinc-900 dark:focus:border-white"
        />
      </div>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <Button type="submit" disabled={!canSubmit}>
        {loading ? "Extracting skills..." : "Extract skills"}
      </Button>
    </form>
  );
}
