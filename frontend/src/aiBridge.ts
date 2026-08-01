import type { AiScenario } from "./aiAssistant";

export interface AiAssistantOpenDetail {
  scenario: AiScenario;
  question?: string;
  projectId?: number | null;
  focusRuntimeSettings?: boolean;
}

export const AI_ASSISTANT_OPEN_EVENT = "akdesk:open-ai-assistant";

export function openAiAssistant(detail: AiAssistantOpenDetail) {
  window.dispatchEvent(
    new CustomEvent<AiAssistantOpenDetail>(AI_ASSISTANT_OPEN_EVENT, { detail }),
  );
}
