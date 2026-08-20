// Thin wrappers around Supabase Auth, called from client components
// (LoginForm / SignupForm / Navbar's logout button).
import { createClient } from "@/lib/supabase/client";

export async function signUpWithPassword(
  email: string,
  password: string,
  fullName: string,
) {
  const supabase = createClient();
  return supabase.auth.signUp({
    email,
    password,
    options: { data: { full_name: fullName } },
  });
}

export async function signInWithPassword(email: string, password: string) {
  const supabase = createClient();
  return supabase.auth.signInWithPassword({ email, password });
}

export async function signOut() {
  const supabase = createClient();
  return supabase.auth.signOut();
}