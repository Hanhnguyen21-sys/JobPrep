import { InputHTMLAttributes, forwardRef } from "react";

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(({ className = "", ...props }, ref) => (
  <input
    ref={ref}
    className={`w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-slate/60 focus:border-blaze ${className}`}
    {...props}
  />
));
Input.displayName = "Input";
