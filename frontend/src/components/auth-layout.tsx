import { CircleCheck, LineChart, Lock, MessageSquareText, ShoppingBag } from "lucide-react";

const POINTS = [
  { icon: MessageSquareText, title: "Reads what you allow", text: "Bank SMS and receipts become transactions — only after you grant each source." },
  { icon: LineChart, title: "Sees what's coming", text: "A 90-day balance forecast with honest uncertainty, bills and subscriptions included." },
  { icon: ShoppingBag, title: "Spends safely", text: "Smart Picks finds products that fit your budget without touching your safety buffer." },
  { icon: Lock, title: "Private by design", text: "Runs on your own computer, offline, with no paid AI and no bank login." },
];

export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="hidden flex-col justify-between bg-[#0f2a4d] p-10 text-white lg:flex">
        <div className="flex items-center gap-2">
          <span className="flex size-9 items-center justify-center rounded-lg bg-white/15"><CircleCheck className="size-5" /></span>
          <span className="text-lg font-semibold">FinPilot AI</span>
        </div>
        <div>
          <h1 className="max-w-md text-4xl font-semibold leading-tight tracking-tight">Your money, understood — with your permission.</h1>
          <ul className="mt-10 grid max-w-lg gap-6">
            {POINTS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/10"><Icon className="size-4" /></span>
                <span>
                  <span className="block font-medium">{title}</span>
                  <span className="block text-sm text-white/70">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-white/50">Sem VII Full Stack Development project · runs locally at ₹0</p>
      </section>
      <section className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">{children}</div>
      </section>
    </div>
  );
}
