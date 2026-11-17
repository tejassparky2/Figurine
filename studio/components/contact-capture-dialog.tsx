"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

export function ContactCaptureDialog({
  open,
  onSave,
}: {
  open: boolean;
  onSave: (whatsapp: string) => Promise<void>;
}) {
  const [whatsapp, setWhatsapp] = useState("");
  const [consented, setConsented] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const digits = whatsapp.replace(/\D/g, "");
  const valid = digits.length >= 10 && digits.length <= 14;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || !consented || saving) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(digits);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save number");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open}>
      <DialogContent
        showCloseButton={false}
        onEscapeKeyDown={(event) => event.preventDefault()}
        onPointerDownOutside={(event) => event.preventDefault()}
      >
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Where should we send your preview?</DialogTitle>
            <DialogDescription>
              Your two design options take about 1–2 minutes. Add WhatsApp so
              your design is saved and our team can help you finish if you
              leave the studio.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-1.5">
            <label htmlFor="lead-whatsapp" className="text-sm font-medium">
              WhatsApp number
            </label>
            <Input
              id="lead-whatsapp"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              autoFocus
              value={whatsapp}
              onChange={(event) => setWhatsapp(event.currentTarget.value)}
              disabled={saving}
              placeholder="10-digit number"
            />
          </div>

          <label className="flex items-start gap-2.5 text-xs leading-relaxed text-muted-foreground">
            <input
              type="checkbox"
              checked={consented}
              onChange={(event) => setConsented(event.currentTarget.checked)}
              disabled={saving}
              className="mt-0.5 size-4 shrink-0 accent-primary"
            />
            <span>
              I agree to receive WhatsApp updates about this design and order.
              No spam.
            </span>
          </label>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <DialogFooter className="mt-5">
            <Button
              type="submit"
              className="w-full sm:w-auto"
              disabled={!valid || !consented || saving}
            >
              {saving && <Spinner className="mr-2 size-4" />}
              Continue to my preview
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
