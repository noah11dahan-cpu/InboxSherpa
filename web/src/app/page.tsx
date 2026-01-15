import Link from "next/link";

export default function Home() {
  return (
    <main className="p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold">InboxSherpa</h1>
      <p className="mt-2 text-gray-600">
        Minimal Day 6 UI — generate a digest and drill into clusters.
      </p>
      <div className="mt-6">
        <Link className="underline" href="/digest">
          Go to Today’s Digest
        </Link>
      </div>
    </main>
  );
}
