import React from "react";

export type CardVariant = "raised" | "inset" | "glass" | "plate";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
}

export function Card({
  variant = "raised",
  className = "",
  children,
  ...rest
}: CardProps) {
  const variantClass =
    variant === "raised"
      ? "neu-raised"
      : variant === "inset"
        ? "neu-inset"
        : variant === "glass"
          ? "glass rounded-[16px]"
          : "skeu-plate";

  return (
    <div className={`${variantClass} p-4 sm:p-5 ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}
