/// <reference types="vite/client" />

// Typed build-time env (the standard Vite augmentation): only VITE_-prefixed
// vars reach the bundle. Optional, not `string` — they may be absent in .env,
// and the supabaseClient fail-loud path is what handles that at runtime.
interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
