import { useState, useEffect, useRef, useCallback } from 'react';

interface WebSocketMessage {
  type: string;
  [key: string]: any;
}

interface UseWebSocketOptions {
  url: string;
  enabled?: boolean;
  onMessage?: (message: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  reconnectDelay?: number;
  maxReconnectAttempts?: number;
}

export function useWebSocket({
  url,
  enabled = true,
  onMessage,
  onConnect,
  onDisconnect,
  onError,
  reconnectDelay = 3000,
  maxReconnectAttempts = 5,
}: UseWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const messageQueueRef = useRef<string[]>([]);
  const reconnectAttemptsRef = useRef(0);

  // Use refs to avoid recreating connect on every render
  const urlRef = useRef(url);
  const enabledRef = useRef(enabled);
  const reconnectDelayRef = useRef(reconnectDelay);
  const maxReconnectAttemptsRef = useRef(maxReconnectAttempts);
  const onMessageRef = useRef(onMessage);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  const onErrorRef = useRef(onError);

  // Sync refs during render (not in effects) for immediate availability
  urlRef.current = url;
  enabledRef.current = enabled;
  reconnectDelayRef.current = reconnectDelay;
  maxReconnectAttemptsRef.current = maxReconnectAttempts;
  onMessageRef.current = onMessage;
  onConnectRef.current = onConnect;
  onDisconnectRef.current = onDisconnect;
  onErrorRef.current = onError;

  const connect = useCallback(() => {
    const currentUrl = urlRef.current;
    const currentEnabled = enabledRef.current;

    if (!currentEnabled || !currentUrl) return;

    // Don't create a new connection if one already exists
    if (wsRef.current && (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN)) {
      console.log('WebSocket already connected or connecting, skipping');
      return;
    }

    try {
      console.log('Opening WebSocket to', currentUrl);
      const ws = new WebSocket(currentUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        onConnectRef.current?.();

        // Send any queued messages
        while (messageQueueRef.current.length > 0) {
          const message = messageQueueRef.current.shift();
          if (message) {
            ws.send(message);
          }
        }
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          onMessageRef.current?.(message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        onErrorRef.current?.(error);
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
        onDisconnectRef.current?.();
        wsRef.current = null;

        // Attempt reconnection
        if (enabledRef.current && reconnectAttemptsRef.current < maxReconnectAttemptsRef.current) {
          reconnectAttemptsRef.current += 1;
          console.log(`Reconnecting in ${reconnectDelayRef.current}ms... (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttemptsRef.current})`);
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectDelayRef.current);
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
    }
  }, []); // No dependencies - everything is via refs

  const sendMessage = useCallback((message: WebSocketMessage) => {
    const messageStr = JSON.stringify(message);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(messageStr);
    } else {
      // Queue the message if not connected
      console.log('WebSocket not connected, queuing message');
      messageQueueRef.current.push(messageStr);

      // Try to reconnect if not already attempting
      if (reconnectAttemptsRef.current >= maxReconnectAttemptsRef.current) {
        reconnectAttemptsRef.current = 0;
        connect();
      }
    }
  }, [connect]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    reconnectAttemptsRef.current = 0;
    setIsConnected(false);
  }, []);

  // Initialize connection when enabled becomes true
  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]); // connect/disconnect are stable (no deps), only react to enabled changes

  return {
    isConnected,
    sendMessage,
    disconnect,
    reconnect: connect,
  };
}
