import { query } from "@anthropic-ai/claude-code";
import type { HookJSONOutput } from "@anthropic-ai/claude-code";
import * as path from "path";
import { FIN_AGENT_PROMPT } from "./fin-agent-prompt";
import { customMCPServer } from "./custom-tools";
import type { SDKMessage, SDKUserMessage } from "./types";

export interface CCQueryOptions {
  maxTurns?: number;
  cwd?: string;
  model?: string;
  allowedTools?: string[];
  appendSystemPrompt?: string;
  mcpServers?: any;
  hooks?: any;
}

export class CCClient {
  private defaultOptions: CCQueryOptions;

  constructor(options?: Partial<CCQueryOptions>) {
    this.defaultOptions = {
      maxTurns: 100,
      cwd: path.join(process.cwd(), 'agent'),
      model: "sonnet",
      allowedTools: [
        "Task", "Bash", "Glob", "Grep", "LS", "ExitPlanMode", "Read", "Edit", "MultiEdit", "Write", "NotebookEdit",
        "WebFetch", "TodoWrite", "WebSearch", "BashOutput", "KillBash", 
        "mcp__finance__extract_statement", "mcp__finance__import_transactions", "mcp__finance__analyze_spending", "mcp__finance__fin_query_sample", "mcp__finance__fin_query_list_saved", "mcp__finance__fin_query_saved", "mcp__finance__fin_query_schema", "mcp__finance__fin_query_sql",
      ],
      appendSystemPrompt: FIN_AGENT_PROMPT,
      mcpServers: {
        "finance": customMCPServer
      },
      hooks: {
        PreToolUse: [
          {
            matcher: "Write|Edit|MultiEdit",
            hooks: [
              async (input: any): Promise<HookJSONOutput> => {
                const toolName = input.tool_name;
                const toolInput = input.tool_input;

                if (!['Write', 'Edit', 'MultiEdit'].includes(toolName)) {
                  return { continue: true };
                }

                let filePath = '';
                if (toolName === 'Write' || toolName === 'Edit') {
                  filePath = toolInput.file_path || '';
                } else if (toolName === 'MultiEdit') {
                  filePath = toolInput.file_path || '';
                }

                const ext = path.extname(filePath).toLowerCase();
                if (ext === '.js' || ext === '.ts' || ext === '.py') {
                  const customScriptsPath = path.join(process.cwd(), 'agent', 'custom_scripts');

                  if (!filePath.startsWith(customScriptsPath)) {
                    return {
                      decision: 'block',
                      stopReason: `Script files (.js, .ts, .py) must be written to the custom_scripts directory. Please use the path: ${customScriptsPath}/${path.basename(filePath)}`,
                      continue: false
                    };
                  }
                }

                return { continue: true };
              }
            ]
          }
        ]
      },
      ...options
    };
  }

  async *queryStream(
    prompt: string | AsyncIterable<SDKUserMessage>,
    options?: Partial<CCQueryOptions>
  ): AsyncIterable<SDKMessage> {
    const mergedOptions = { ...this.defaultOptions, ...options };

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
