import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export function NotFoundPage() {
  return (
    <Card className="mx-auto mt-10 max-w-lg p-8 text-center">
      <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-violet-400/20 bg-violet-500/10 text-violet-200">
        <Compass className="h-7 w-7" aria-hidden="true" />
      </span>
      <p className="mt-4 font-mono text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
        404
      </p>
      <h1 className="mt-2 font-display text-2xl font-semibold text-white">
        That page is not on the table
      </h1>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-400">
        The address may be mistyped, or the room may have moved back to its
        lobby. Return home and pick up from there.
      </p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        <Link to="/">
          <Button variant="secondary">Back home</Button>
        </Link>
        <Link to="/join">
          <Button>Join a room</Button>
        </Link>
      </div>
    </Card>
  );
}
