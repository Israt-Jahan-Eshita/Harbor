"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Skeleton } from "@/components/ui";

export default function TodayRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/menu");
  }, [router]);

  return (
    <div className="py-10">
      <Skeleton className="h-32 rounded-[20px]" />
    </div>
  );
}

