import { signIn } from "@/auth";

export default function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string }>;
}) {
  return (
    <div className="relative mx-auto flex max-w-md flex-col items-center gap-6 overflow-hidden rounded-2xl border border-white/10 bg-zinc-950 p-10 py-16 text-center shadow-2xl">
      <div
        aria-hidden
        className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(99,102,241,0.25),transparent_55%)]"
      />
      <div
        aria-hidden
        className="absolute inset-0 bg-[radial-gradient(circle_at_bottom_right,rgba(244,63,94,0.18),transparent_55%)]"
      />

      <div className="relative flex flex-col items-center gap-3">
        <span
          aria-hidden
          className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 text-2xl shadow-lg shadow-indigo-900/50"
        >
          🃏
        </span>
        <h1 className="text-3xl font-bold leading-tight text-white">MTG Helper</h1>
        <p className="max-w-xs text-sm text-gray-400">
          AI-powered Commander deck builder. Sign in to get started.
        </p>
      </div>

      <form
        className="relative w-full"
        action={async () => {
          "use server";
          const params = await searchParams;
          await signIn("google", { redirectTo: params.callbackUrl ?? "/" });
        }}
      >
        <button
          type="submit"
          className="w-full rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white shadow-lg shadow-indigo-900/40 transition-colors hover:bg-indigo-500"
        >
          Continue with Google
        </button>
      </form>
    </div>
  );
}
