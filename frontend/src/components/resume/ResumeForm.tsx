"use client";

import { ChangeEvent, DragEvent, FormEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type InputMode = "text" | "file";

const ACCEPTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".pdf"];
const ACCEPTED_MIME_TYPES = ["image/png", "image/jpeg", "application/pdf"];
// Kept in sync with backend/app/api/routes/resumes.py's MAX_FILE_BYTES --
// checked client-side too so an obviously-too-large file gets rejected
// before spending a round trip on it.
const MAX_FILE_BYTES = 5 * 1024 * 1024;

function isAcceptedFile(file: File): boolean {
  const nameOk = ACCEPTED_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext));
  const typeOk = ACCEPTED_MIME_TYPES.includes(file.type);
  return nameOk && typeOk;
}

interface ResumeFormProps {
  onSubmitText: (text: string, targetPosition: string) => void;
  onSubmitFile: (file: File, targetPosition: string) => void;
  loading: boolean;
  error: string | null;
}

// One resume-import workflow, two input methods -- both converge on the
// same onSubmit* callbacks (wired to useResume's submitResume/
// submitResumeFile in app/resume/page.tsx), which share one
// skills/loading/error state, so the result below never needs to know
// which method produced it.
export function ResumeForm({ onSubmitText, onSubmitFile, loading, error }: ResumeFormProps) {
  const [mode, setMode] = useState<InputMode>("text");
  const [targetPosition, setTargetPosition] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function pickFile(candidate: File | undefined) {
    if (!candidate) return;
    if (!isAcceptedFile(candidate)) {
      setFile(null);
      setFileError("Unsupported file type -- please upload a PNG, JPG/JPEG image, or a PDF.");
      return;
    }
    if (candidate.size > MAX_FILE_BYTES) {
      setFile(null);
      setFileError(
        `That file is too large -- please upload one under ${MAX_FILE_BYTES / (1024 * 1024)} MB.`,
      );
      return;
    }
    setFileError(null);
    setFile(candidate);
  }

  function handleFileInputChange(e: ChangeEvent<HTMLInputElement>) {
    pickFile(e.target.files?.[0]);
  }

  function handleDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    pickFile(e.dataTransfer.files?.[0]);
  }

  function removeFile() {
    setFile(null);
    setFileError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!targetPosition.trim()) return;

    if (mode === "text") {
      if (!text.trim()) return;
      onSubmitText(text, targetPosition.trim());
    } else {
      if (!file) return;
      onSubmitFile(file, targetPosition.trim());
    }
  }

  const canSubmit =
    !loading &&
    !!targetPosition.trim() &&
    (mode === "text" ? !!text.trim() : !!file);

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label
          htmlFor="target-position"
          className="mb-1 block text-sm font-medium text-ink"
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
        <p className="mb-2 block text-sm font-medium text-ink">Add your resume</p>
        <div className="inline-flex rounded-md border border-line p-0.5">
          <button
            type="button"
            onClick={() => setMode("text")}
            className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
              mode === "text" ? "bg-ink text-paper" : "text-slate hover:text-ink"
            }`}
          >
            Paste text
          </button>
          <button
            type="button"
            onClick={() => setMode("file")}
            className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
              mode === "file" ? "bg-ink text-paper" : "text-slate hover:text-ink"
            }`}
          >
            Upload file
          </button>
        </div>
      </div>

      {mode === "text" ? (
        <div>
          <label
            htmlFor="resume-text"
            className="mb-1 block text-sm font-medium text-ink"
          >
            Paste your resume text
          </label>
          <textarea
            id="resume-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={14}
            placeholder="Paste the text of your resume here..."
            className="w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-slate/60 focus:border-blaze"
          />
        </div>
      ) : (
        <div>
          <label
            htmlFor="resume-file"
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            className="flex cursor-pointer flex-col items-center gap-2 rounded-md border border-dashed border-line bg-paper px-4 py-8 text-center transition-colors hover:border-blaze"
          >
            <span className="text-sm font-medium text-ink">
              Click to choose a file, or drag one here
            </span>
            <span className="text-xs text-slate">PNG, JPG, JPEG, or PDF</span>
            <input
              ref={fileInputRef}
              id="resume-file"
              type="file"
              accept={ACCEPTED_EXTENSIONS.join(",")}
              onChange={handleFileInputChange}
              className="hidden"
            />
          </label>

          {file && (
            <div className="mt-2 flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2 text-sm">
              <span className="truncate text-ink" title={file.name}>
                {file.name}
              </span>
              <Button type="button" variant="ghost" onClick={removeFile}>
                Remove
              </Button>
            </div>
          )}

          {fileError && <p className="mt-2 text-sm text-danger">{fileError}</p>}
        </div>
      )}

      {error && <p className="text-sm text-danger">{error}</p>}

      <Button type="submit" disabled={!canSubmit}>
        {loading ? "Extracting skills..." : "Extract skills"}
      </Button>
    </form>
  );
}
