"use client";
/**
 * Model choice as a small text button in the composer's bottom-left, revealing a popover
 * [proposal, B2]: choosing after sending is too late, but two full-width selects in
 * prime space were too much. Sonnet 5.5 is the conversation default (owner decision).
 */
import { Check, ChevronDown } from "lucide-react";
import { Popover, PopoverClose, PopoverContent, PopoverItem, PopoverTrigger } from "@/components/primitives";

export const MODELS = [
  { id: "claude-sonnet-5-5", label: "Sonnet 5.5", note: "Default · balanced" },
  { id: "claude-opus-5-5", label: "Opus 5.5", note: "Stronger · about 2× the cost" },
  { id: "claude-fable-5-2", label: "Fable 5.2", note: "Strongest · about 4× the cost" },
  { id: "claude-haiku-5-5", label: "Haiku 5.5", note: "Fastest · cheapest" },
] as const;
export const DEFAULT_MODEL = MODELS[0].id;

export function modelLabel(id: string): string {
  return MODELS.find((m) => m.id === id)?.label ?? MODELS[0].label;
}

export function ModelPicker({ model, onModel }: { model: string; onModel: (id: string) => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Model: ${modelLabel(model)}`}
          className="flex h-8 items-center gap-1 rounded-md px-2 text-xs text-text-2 hover:bg-surface-3"
        >
          {modelLabel(model)}
          <ChevronDown className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64">
        {MODELS.map((m) => (
          <PopoverClose asChild key={m.id}>
            <PopoverItem onClick={() => onModel(m.id)} aria-checked={m.id === model} role="menuitemradio">
              <span className="flex-1">
                {m.label}
                <span className="ml-2 text-xs text-text-2">{m.note}</span>
              </span>
              {m.id === model ? <Check className="size-4" /> : null}
            </PopoverItem>
          </PopoverClose>
        ))}
      </PopoverContent>
    </Popover>
  );
}
