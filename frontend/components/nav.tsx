import Link from "next/link";

export function Nav() {
  return (
    <nav className="border-b border-white/10 bg-black/40 backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 overflow-x-auto">
        <Link href="/decks" className="text-lg font-bold tracking-tight text-white">
          MTG Helper
        </Link>
        <Link
          href="/decks"
          className="text-sm text-gray-400 hover:text-white transition-colors flex-shrink-0"
        >
          Decks
        </Link>
        <Link
          href="/preferences"
          className="text-sm text-gray-400 hover:text-white transition-colors flex-shrink-0"
        >
          Preferences
        </Link>
      </div>
    </nav>
  );
}
