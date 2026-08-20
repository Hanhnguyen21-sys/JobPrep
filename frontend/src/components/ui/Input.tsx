import { InputHTMLAttributes, forwardRef } from "react";

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(({ className = "", ...props }, ref) => (
  <input
    ref={ref}
    className={`w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-black dark:border-zinc-700 dark:bg-zinc-900 dark:focus:border-white ${className}`}
    {...props}
  />
));
Input.displayName = "Input";
