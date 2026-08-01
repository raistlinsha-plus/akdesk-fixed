import type { WorkspaceMode } from "./workspaceMode";

export const EXPERIENCE_PROFILE_KEY = "akdesk.experience-profile.v1";

export type ExperienceProfileId = "market" | "rates" | "credit" | "global";

export interface ExperienceProfile {
  id: ExperienceProfileId;
  label: string;
  kicker: string;
  description: string;
  mode: WorkspaceMode;
  landingPage: string;
  action: string;
}

export const EXPERIENCE_PROFILES: ExperienceProfile[] = [
  {
    id: "market",
    label: "每日看市场",
    kicker: "MARKET",
    description: "先看可信异动，再回到资金、曲线、现券、期货和外汇原始模块。",
    mode: "market",
    landingPage: "market-changes",
    action: "进入市场变化",
  },
  {
    id: "rates",
    label: "利率与宏观研究",
    kicker: "RATES",
    description: "从研究首页进入专题、项目、FRED、图表研究和复盘闭环。",
    mode: "research",
    landingPage: "research-desk",
    action: "进入研究首页",
  },
  {
    id: "credit",
    label: "信用观察",
    kicker: "CREDIT",
    description: "优先进入信用观察 R2，跟踪主体、单券、组合、信号和复核日程。",
    mode: "market",
    landingPage: "credit",
    action: "进入信用观察",
  },
  {
    id: "global",
    label: "全球跨市场",
    kicker: "GLOBAL",
    description: "从外汇进入 FRED、World Bank、跨市场图表与数据发布复盘。",
    mode: "market",
    landingPage: "fx",
    action: "进入外汇市场",
  },
];

export function experienceProfile(
  id: ExperienceProfileId | null,
): ExperienceProfile | null {
  return EXPERIENCE_PROFILES.find((item) => item.id === id) ?? null;
}

export function readExperienceProfile(
  storage: Pick<Storage, "getItem"> | undefined,
): ExperienceProfileId | null {
  if (!storage) return null;
  try {
    const value = storage.getItem(EXPERIENCE_PROFILE_KEY);
    return EXPERIENCE_PROFILES.some((item) => item.id === value)
      ? value as ExperienceProfileId
      : null;
  } catch {
    return null;
  }
}

export function writeExperienceProfile(
  storage: Pick<Storage, "setItem"> | undefined,
  id: ExperienceProfileId,
): void {
  try {
    storage?.setItem(EXPERIENCE_PROFILE_KEY, id);
  } catch {
    // The profile is a convenience preference; the app remains usable.
  }
}

