import { describe, expect, it } from "vitest";

import { cardIdentity } from "./card-identity";

describe("cardIdentity", () => {
  it("uses oracle identity across printings", () => {
    expect(cardIdentity({ scryfall_id: "printing-a", oracle_id: "oracle" })).toBe("oracle");
    expect(cardIdentity({ scryfall_id: "printing-b", oracle_id: "oracle" })).toBe("oracle");
  });

  it("falls back to scryfall identity", () => {
    expect(cardIdentity({ scryfall_id: "printing", oracle_id: null })).toBe("printing");
  });
});
