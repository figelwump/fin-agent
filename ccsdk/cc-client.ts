import { query } from "@anthropic-ai/claude-agent-sdk";
import type { HookJSONOutput } from "@anthropic-ai/claude-agent-sdk";
import * as path from "path";
import { FIN_AGENT_PROMPT } from "./fin-agent-prompt";
import type { SDKMessage, SDKUserMessage } from "./types";

function buildVenvEnv(baseEnv?: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env, ...(baseEnv ?? {}) };

  const projectRoot = process.cwd();
  const venvPath = path.join(projectRoot, '.venv');
  const binDir = path.join(venvPath, 'bin');

  const pathValue = env.PATH ?? '';
  const pathSegments = pathValue ? pathValue.split(':') : [];
  if (!pathSegments.includes(binDir)) {
    env.PATH = pathValue ? `${binDir}:${pathValue}` : binDir;
  }

  if (!env.VIRTUAL_ENV) {
    env.VIRTUAL_ENV = venvPath;
  }

  return env;
}

export interface CCQueryOptions {
  maxTurns?: number;
  cwd?: string;
  model?: string;
  includePartialMessages?: boolean;
  allowedTools?: string[];
  appendSystemPrompt?: string;
  hooks?: any;
  env?: NodeJS.ProcessEnv;
  settingSources?: string[];
}

export class CCClient {
  private defaultOptions: CCQueryOptions;

  constructor(options?: Partial<CCQueryOptions>) {
    this.defaultOptions = {
      maxTurns: 100,
      cwd: process.cwd(),
      model: "sonnet",
      includePartialMessages: true,
      allowedTools: [
        "Task", "Bash", "Glob", "Grep", "LS", "ExitPlanMode", "Read", "Edit", "MultiEdit", "Write", "NotebookEdit",
        "WebFetch", "TodoWrite", "WebSearch", "BashOutput", "KillBash", 
        "Skill",
      ],
      appendSystemPrompt: FIN_AGENT_PROMPT,
      settingSources: ["project", "user"], // Load project and user-level skills
      hooks: {
        PreToolUse: [
          {
            matcher: "Write|Edit|MultiEdit",
            // Only allow file writes/edits to paths under ~/.finagent; block all others, regardless of file type.
            hooks: [
              async (input: any): Promise<HookJSONOutput> => {
                const toolName = input.tool_name;
                const toolInput = input.tool_input;

                if (!['Write', 'Edit', 'MultiEdit'].includes(toolName)) {
                  return { continue: true };
                }

                // Normalize path (handle tilde or relative paths)
                let filePath = '';
                if (toolName === 'Write' || toolName === 'Edit') {
                  filePath = toolInput.file_path || '';
                } else if (toolName === 'MultiEdit') {
                  filePath = toolInput.file_path || '';
                }

                // Resolve home directory if ~ is used
                let homeDir = process.env.HOME || process.env.USERPROFILE || '';
                const normalizedFinagentPath = path.resolve(homeDir, '.finagent');
                let normalizedFilePath: string;
                if (filePath.startsWith('~')) {
                  // Expand tilde to home directory
                  normalizedFilePath = path.resolve(homeDir, filePath.slice(1));
                } else {
                  normalizedFilePath = path.resolve(filePath);
                }

                if (!normalizedFilePath.startsWith(normalizedFinagentPath + path.sep)) {
                  return {
                    decision: 'block',
                    stopReason: `Writes and edits are only allowed inside the ~/.finagent directory. Please use a path under: ${normalizedFinagentPath}/`,
                    continue: false
                  };
                }

                return { continue: true };
              }
            ]
          }
        ]
      },
      env: buildVenvEnv(options?.env),
      ...options
    };

    this.defaultOptions.env = buildVenvEnv(this.defaultOptions.env);
  }

  async *queryStream(
    prompt: string | AsyncIterable<SDKUserMessage>,
    options?: Partial<CCQueryOptions>
  ): AsyncIterable<SDKMessage> {
    const mergedOptions = { ...this.defaultOptions, ...options };
    mergedOptions.env = buildVenvEnv(mergedOptions.env);
    mergedOptions.includePartialMessages = true;

    for await (const message of query({
      prompt,
      options: mergedOptions
    })) {
      yield message;
    }
  }

  async querySingle(prompt: string, options?: Partial<CCQueryOptions>): Promise<{
    messages: SDKMessage[];
    cost: number;
    duration: number;
  }> {
    const messages: SDKMessage[] = [];
    let totalCost = 0;
    let duration = 0;

    for await (const message of this.queryStream(prompt, options)) {
      messages.push(message);

      if (message.type === "result" && message.subtype === "success") {
        totalCost = message.total_cost_usd;
        duration = message.duration_ms;
      }
    }

    return { messages, cost: totalCost, duration };
  }
}
