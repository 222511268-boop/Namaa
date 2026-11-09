import { AppShell } from "@/components/app-shell";
import { SessionProvider } from "@/components/session";
import { Logo, Spinner } from "@/components/ui";

function Loading() {
  return (
    <div className="grid min-h-screen place-items-center">
      <div className="flex flex-col items-center gap-4 text-muted">
        <Logo />
        <Spinner className="h-5 w-5" />
      </div>
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider fallback={<Loading />}>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
