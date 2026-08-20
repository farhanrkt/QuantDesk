import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl items-center px-4">
      <div className="w-full rounded border border-dashed border-rule px-6 py-16 text-center">
        <p className="eyebrow mb-2">404 — no such route</p>
        <p className="mx-auto max-w-md text-sm leading-relaxed text-ash">
          Nothing is served from this path. The desk lives at the root, and every engine is
          driven from the ticker bar there.
        </p>
        <Link
          href="/"
          className="mt-6 inline-flex h-9 items-center rounded border border-tech/50 bg-tech/10 px-4 font-mono text-[0.65rem] uppercase tracking-[0.14em] text-chalk transition-colors hover:bg-tech/20"
        >
          Back to the desk
        </Link>
      </div>
    </main>
  );
}
