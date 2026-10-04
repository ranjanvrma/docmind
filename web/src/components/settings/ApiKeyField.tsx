import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, Loader2, PlugZap, XCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge, Input } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { keys } from "@/lib/queries";
import type { SettingsView } from "@/lib/types";

/**
 * Write-only API key control. The key is sent once over the API and stored
 * server-side; it is never returned, so the UI only knows whether one is set
 * and where it came from.
 */
export function ApiKeyField({ status, disabledTest }: { status: SettingsView["llm_api_key"]; disabledTest: boolean }) {
  const client = useQueryClient();
  const [value, setValue] = useState("");
  const refresh = (view: SettingsView) => {
    client.setQueryData(keys.settings, view);
    client.invalidateQueries({ queryKey: keys.health });
  };

  const save = useMutation({
    mutationFn: (key: string) => api.updateSettings({ llm_api_key: key }),
    onSuccess: (view) => {
      refresh(view);
      setValue("");
      toast.success("API key saved");
    },
    onError: (e) => toast.error(describeError(e).detail ?? describeError(e).title),
  });
  const remove = useMutation({
    mutationFn: api.removeSavedLlmKey,
    onSuccess: (view) => {
      refresh(view);
      toast.success("Saved key removed");
    },
  });
  const test = useMutation({ mutationFn: api.testLlm });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) save.mutate(value.trim());
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <KeyRound className="size-4 text-fg-faint" />
        {status.configured ? (
          <Badge tone="success">Configured · {status.source === "settings" ? "saved here" : "from server .env"}</Badge>
        ) : status.withheld ? (
          <Badge tone="warning">Server key not sent to this endpoint · enter a key for it</Badge>
        ) : (
          <Badge tone="warning">Not configured</Badge>
        )}
        {status.source === "settings" && (
          <button type="button" onClick={() => remove.mutate()} className="text-xs text-fg-muted underline-offset-2 hover:text-danger hover:underline">
            Remove saved key
          </button>
        )}
      </div>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <Input
          type="password"
          autoComplete="off"
          aria-label="LLM API key"
          placeholder={status.configured ? "Paste a new key to replace it" : "Paste your provider API key"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <Button type="submit" variant="glass" disabled={!value.trim() || save.isPending}>
          {save.isPending ? <Loader2 className="animate-spin" /> : null} Save key
        </Button>
      </form>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" onClick={() => test.mutate()} disabled={test.isPending || disabledTest}>
          {test.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />} Test connection
        </Button>
        {disabledTest && <span className="text-xs text-fg-faint">Save your changes first.</span>}
        {test.data &&
          (test.data.ok ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-success">
              <CheckCircle2 className="size-3.5" /> Connected to {test.data.model} in {test.data.latency_ms} ms
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-xs text-danger">
              <XCircle className="size-3.5" /> {test.data.message}
            </span>
          ))}
        {test.error && <span className="text-xs text-danger">{describeError(test.error).title}</span>}
      </div>
      <p className="text-xs text-fg-faint">The key is stored on the server (in its data folder) and is never sent back to the browser.</p>
    </div>
  );
}
