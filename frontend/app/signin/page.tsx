import { signIn } from "@/auth";

export default function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string }>;
}) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-6 py-20">
      <h1 className="text-2xl font-bold text-white">Sign in to MTG Helper</h1>
      <p className="text-sm text-gray-400">Continue with your Google account.</p>
      <form
        action={async () => {
          "use server";
          const params = await searchParams;
          await signIn("google", { redirectTo: params.callbackUrl ?? "/" });
        }}
      >
        <button
          type="submit"
          className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white hover:bg-indigo-500 transition-colors"
        >
          Continue with Google
        </button>
      </form>
    </div>
  );
}
