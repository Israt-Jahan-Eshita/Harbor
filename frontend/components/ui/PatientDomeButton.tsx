"use client";

import React from "react";
import { Check } from "lucide-react";

export interface PatientDomeButtonProps {
  label: string;
  confirmedLabel?: string;
  confirmed?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  "data-testid"?: string;
}

export function PatientDomeButton({
  label,
  confirmedLabel,
  confirmed = false,
  disabled = false,
  onClick,
  "data-testid": testId,
}: PatientDomeButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || confirmed}
      onClick={onClick}
      data-testid={testId}
      className="skeu-dome mx-auto flex h-52 w-52 sm:h-60 sm:w-60 flex-col items-center justify-center rounded-full text-center cursor-pointer disabled:cursor-default"
      style={
        confirmed
          ? {
              background:
                "radial-gradient(circle at 35% 28%, var(--saffron) 0%, var(--ok) 100%)",
              color: "var(--on-ok)",
              borderColor: "var(--ok)",
            }
          : undefined
      }
    >
      {confirmed ? (
        <>
          <Check className="h-12 w-12 mb-2 stroke-[3]" aria-hidden="true" />
          <span className="text-2xl font-extrabold px-4">
            {confirmedLabel || label}
          </span>
        </>
      ) : (
        <span className="text-3xl sm:text-4xl font-extrabold tracking-wide px-4">
          {label}
        </span>
      )}
    </button>
  );
}

