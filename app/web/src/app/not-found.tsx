import Link from "next/link";
export default function NotFound() {
  return (
    <div className="empty">
      <h1>A little off the path.</h1>
      <p>This page isn’t in your workspace.</p>
      <Link className="button" href="/today">
        Back to today
      </Link>
    </div>
  );
}
