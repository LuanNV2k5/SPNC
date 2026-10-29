import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { contractEvents } from "./contract";

const FIXTURE = resolve(process.cwd(), "src/trace/contract-fixtures.json");

describe("trace contract fixture (AC-20A-09)", () => {
  it("contract-fixtures.json is what the payload builders produce", () => {
    const built = JSON.stringify({ events: contractEvents() }, null, 2) + "\n";
    // UPDATE_CONTRACT=1 npm test rewrites the fixture after a deliberate payload change
    if (process.env.UPDATE_CONTRACT === "1") writeFileSync(FIXTURE, built);
    expect(readFileSync(FIXTURE, "utf-8").replace(/\r\n/g, "\n")).toBe(built);
  });
});
