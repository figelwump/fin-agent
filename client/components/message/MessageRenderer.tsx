import React from 'react';
import { Message, StructuredPrompt } from './types';
import { UserMessage } from './UserMessage';
import { SystemMessage } from './SystemMessage';
import { AssistantMessage } from './AssistantMessage';

interface MessageRendererProps {
  message: Message;
  onSendMessage?: (message: StructuredPrompt | string) => void;
}

export function MessageRenderer({ message, onSendMessage }: MessageRendererProps) {
  switch (message.type) {
    case 'user':
      return <UserMessage message={message} />;

    case 'system':
      return <SystemMessage message={message} />;

    case 'assistant':
      return <AssistantMessage message={message} onSendMessage={onSendMessage} />;
    
    default:
      return (
        <div className="mb-4 p-4 bg-red-50 border-l-4 border-red-400 rounded-r-lg">
          <div className="text-red-700">
            Unknown message type: {(message as any).type}
          </div>
          <pre className="text-sm mt-2 text-gray-600">
            {JSON.stringify(message, null, 2)}
          </pre>
        </div>
      );
  }
}

export * from './types';
export { UserMessage } from './UserMessage';
export { SystemMessage } from './SystemMessage';
export { AssistantMessage } from './AssistantMessage';
