import { describe, expect, it } from "vitest";
import {
  EXPERIENCE_PROFILE_KEY,
  EXPERIENCE_PROFILES,
  defaultLandingPage,
  experienceProfile,
  readExperienceProfile,
  writeExperienceProfile,
} from "./experienceProfiles";

describe("experience profiles", () => {
  it("maps four jobs to modes and distinct landing pages", () => {
    expect(EXPERIENCE_PROFILES).toHaveLength(4);
    expect(new Set(EXPERIENCE_PROFILES.map((item) => item.landingPage)).size).toBe(4);
    expect(experienceProfile("rates")?.mode).toBe("research");
    expect(experienceProfile("credit")?.landingPage).toBe("credit");
  });

  it("persists only a supported profile", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    writeExperienceProfile(storage, "global");
    expect(readExperienceProfile(storage)).toBe("global");
    values.set(EXPERIENCE_PROFILE_KEY, "unknown");
    expect(readExperienceProfile(storage)).toBeNull();
  });

  it("defaults fresh browsers to the weekly task without overriding existing preferences", () => {
    expect(defaultLandingPage(null, null, null)).toBe("cross-asset-week");
    expect(defaultLandingPage(null, "market", null)).toBe("dashboard");
    expect(defaultLandingPage(null, "research", null)).toBe("research-desk");
    expect(defaultLandingPage(experienceProfile("credit"), "market", null)).toBe("credit");
    expect(defaultLandingPage(experienceProfile("credit"), "market", "research")).toBe("research-desk");
  });
});

