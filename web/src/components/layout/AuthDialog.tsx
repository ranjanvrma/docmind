import { useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/overlays";
import { Input } from "@/components/ui/primitives";
import { on } from "@/lib/events";
import { useHealth } from "@/lib/queries";
import { usePreferences } from "./PreferencesProvider";

/**
 * Asks for the API access token when the server requires one (DOCMIND_API_TOKEN)
 * and none is stored, or whenever the API answers 401.
 */
export function AuthDialog() {
  const { data: health } = useHealth();
  const { hasToken, setToken } = usePreferences();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [remember, setRemember] = useState(false);

  useEffect(() => on("auth-required", () => setOpen(true)), []);
  useEffect(() => {
    if (health?.auth_required && !hasToken) setOpen(true);
  }, [health?.auth_required, hasToken]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!value.trim()) return;
    setToken(value.trim(), remember);
    setValue("");
    setOpen(false);
    client.invalidateQueries();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <div className="mb-4 flex size-10 items-center justify-center rounded-xl border border-line bg-accent-soft text-accent">
          <KeyRound className="size-5" />
        </div>
        <DialogTitle className="text-lg font-semibold">Access token required</DialogTitle>
        <DialogDescription className="mt-1.5 text-sm text-fg-muted">
          This DocMind server is protected. Enter the access token configured by its administrator
          (<code className="font-mono text-xs">DOCMIND_API_TOKEN</code>).
        </DialogDescription>
        <form onSubmit={submit} className="mt-5 space-y-4">
          <Input
            type="password"
            autoComplete="off"
            placeholder="Access token"
            aria-label="Access token"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
          />
          <label className="flex items-center gap-2 text-sm text-fg-muted">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="accent-[var(--accent)]" />
            Remember on this device
          </label>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!value.trim()}>
              Save token
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
