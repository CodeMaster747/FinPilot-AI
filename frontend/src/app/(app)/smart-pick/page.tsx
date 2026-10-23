"use client";

import { useMutation } from "@tanstack/react-query";
import { ExternalLink, LoaderCircle, Search, Sparkles, Star } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/app-shell";
import { Card, EmptyState, Pill } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { post } from "@/lib/api";
import { ago, inr } from "@/lib/format";

type Product = {
  title: string; price: number | null; url: string | null; store: string | null; rating: number | null;
  reviews: number | string | null; image: string | null; delivery: string | null; snippet: string | null;
  affordability: "buy_now" | "save_up" | "not_now" | "needs_price"; affordability_text: string;
};
type SearchResult = { query: string; checked_at: string; products: Product[] };

const TIER: Record<Product["affordability"], { label: string; tone: "good" | "warn" | "bad" | "neutral" }> = {
  buy_now: { label: "Fits your budget", tone: "good" },
  save_up: { label: "Save up", tone: "warn" },
  not_now: { label: "Not right now", tone: "bad" },
  needs_price: { label: "Price unavailable", tone: "neutral" },
};

export default function SmartPickPage() {
  const [query, setQuery] = useState("");
  const search = useMutation({ mutationFn: () => post<SearchResult>("/smart-pick/search", { query: query.trim() }) });
  return (
    <div className="grid gap-5">
      <PageHeader title="Smart Pick" description="Find real product listings and see how each fits your budget. FinPilot does not accept affiliate fees or paid placement." />
      <Card title="What are you looking for?" description="Search Google Shopping listings in India. Check the retailer page for the latest price and availability.">
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); if (query.trim().length >= 2) search.mutate(); }}>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. wireless headphones under ₹5,000" aria-label="Product search" minLength={2} maxLength={160} required />
          <Button type="submit" disabled={search.isPending || query.trim().length < 2}>
            {search.isPending ? <LoaderCircle className="animate-spin" /> : <Search />} Search products
          </Button>
        </form>
      </Card>

      {search.error && <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive" role="alert">{search.error.message}</p>}
      {search.data && (
        <section className="grid gap-3" aria-live="polite">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Results for “{search.data.query}”</h2>
            <span className="text-xs text-muted-foreground">Checked {ago(search.data.checked_at)} · Google Shopping</span>
          </div>
          {search.data.products.length === 0 ? <EmptyState icon={Search} title="No listings found">Try a shorter or more specific search.</EmptyState> : (
            <ul className="grid gap-3 lg:grid-cols-2">
              {search.data.products.map((product, i) => {
                const tier = TIER[product.affordability];
                return <li key={`${product.url}-${i}`} className="rounded-xl border border-border bg-card p-4">
                  <div className="flex gap-3">
                    {product.image && <img src={product.image} alt="" className="size-20 shrink-0 rounded-lg bg-white object-contain" loading="lazy" />}
                    <div className="min-w-0 flex-1">
                      <div className="font-medium leading-snug">{product.title}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{product.store || "Retailer listing"}</div>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {product.price !== null ? <span className="font-semibold tabular">{inr(product.price)}</span> : <span className="text-sm text-muted-foreground">Price unavailable</span>}
                        {product.rating != null && <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><Star className="size-3 fill-current" />{product.rating}{product.reviews ? ` (${product.reviews})` : ""}</span>}
                        <Pill tone={tier.tone}>{tier.label}</Pill>
                      </div>
                    </div>
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">{product.affordability_text}</p>
                  {product.delivery && <p className="mt-1 text-xs text-muted-foreground">{product.delivery}</p>}
                  {product.url && <a href={product.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">Check retailer listing <ExternalLink className="size-3.5" /></a>}
                </li>;
              })}
            </ul>
          )}
          <p className="text-xs text-muted-foreground"><Sparkles className="mr-1 inline size-3" />Listings and prices come from Google Shopping and may change. FinPilot ranks them using your budget and forecast; verify details with the retailer.</p>
        </section>
      )}
      {!search.data && !search.isPending && <EmptyState icon={Sparkles} title="Product recommendations, grounded in live listings">Search for a product to compare current retailer listings against your safe-to-spend.</EmptyState>}
    </div>
  );
}
