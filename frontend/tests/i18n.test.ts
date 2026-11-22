import { describe, expect, it } from "vitest";
import { formatLocalizedNumber, translateKey } from "@/lib/i18n";
import bnMessages from "@/messages/bn.json";
import enMessages from "@/messages/en.json";

function collectLeafKeys(obj: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      keys.push(...collectLeafKeys(v as Record<string, unknown>, path));
    } else {
      keys.push(path);
    }
  }
  return keys.sort();
}

describe("i18n translation parity and formatting", () => {
  it("bn.json and en.json have identical key sets with no empty strings", () => {
    const bnKeys = collectLeafKeys(bnMessages);
    const enKeys = collectLeafKeys(enMessages);
    expect(bnKeys).toEqual(enKeys);
    expect(bnKeys.length).toBeGreaterThan(50);

    for (const key of bnKeys) {
      expect(translateKey("bn", key).length).toBeGreaterThan(0);
      expect(translateKey("en", key).length).toBeGreaterThan(0);
    }
  });

  it("formats numbers in Bangla numerals for bn and ASCII for en", () => {
    expect(formatLocalizedNumber(1250, "bn")).toBe("১,২৫০");
    expect(formatLocalizedNumber(1250, "en")).toBe("1,250");
  });
});

