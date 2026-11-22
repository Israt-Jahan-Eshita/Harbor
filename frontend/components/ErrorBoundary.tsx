"use client";

import React from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface ErrorBoundaryState {
  hasError: boolean;
}

class ErrorBoundaryInner extends React.Component<
  { children: React.ReactNode; fallbackTitle: string; retryLabel: string },
  ErrorBoundaryState
> {
  constructor(props: {
    children: React.ReactNode;
    fallbackTitle: string;
    retryLabel: string;
  }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="mx-auto my-12 max-w-md p-6 neu-raised text-center space-y-4">
          <AlertTriangle
            className="mx-auto h-10 w-10"
            style={{ color: "var(--danger)" }}
            aria-hidden="true"
          />
          <p className="text-lg font-semibold" style={{ color: "var(--text)" }}>
            {this.props.fallbackTitle}
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false })}
            className="skeu-button inline-flex min-h-[48px] items-center gap-2 px-5 py-2.5 font-semibold"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            {this.props.retryLabel}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function ErrorBoundary({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <ErrorBoundaryInner
      fallbackTitle={t("common.errorUnexpected")}
      retryLabel={t("common.retry")}
    >
      {children}
    </ErrorBoundaryInner>
  );
}

