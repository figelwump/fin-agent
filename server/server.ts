import "dotenv/config";
import { WebSocketHandler } from "../ccsdk/websocket-handler";
import type { WSClient } from "../ccsdk/types";
import { DATABASE_PATH } from "../database/config";
import { bulkImportStatements, getImportsStagingDir, sanitiseRelativePath, writeUploadedFile } from "../ccsdk/bulk-import";
import * as path from "path";
import * as fs from "fs/promises";

const wsHandler = new WebSocketHandler(DATABASE_PATH);

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const server = Bun.serve({
  port: 3000,
  idleTimeout: 120,

  websocket: {
    open(ws: WSClient) {
      wsHandler.onOpen(ws);
    },

    message(ws: WSClient, message: string) {
      wsHandler.onMessage(ws, message);
    },

    close(ws: WSClient) {
      wsHandler.onClose(ws);
    }
  },

  async fetch(req: Request, server: any) {
    const url = new URL(req.url);

    if (req.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    if (url.pathname === '/ws') {
      const upgraded = server.upgrade(req, { data: { sessionId: '' } });
      if (!upgraded) {
        return new Response('WebSocket upgrade failed', { status: 400 });
      }
      return;
    }

    if (url.pathname === '/') {
      const file = Bun.file('./client/index.html');
      return new Response(file, {
        headers: {
          'Content-Type': 'text/html',
        },
      });
    }

    if (url.pathname === '/api/bulk-import' && req.method === 'POST') {
      let stagingDir: string | undefined;
      try {
        const formData = await req.formData();
        const autoApproveRaw = formData.get('autoApprove');
        const autoApprove = typeof autoApproveRaw === 'string' ? autoApproveRaw === 'true' : false;
        const fileEntries = formData.getAll('files');

        if (fileEntries.length === 0) {
          return new Response(JSON.stringify({ error: 'No files uploaded.' }), {
            status: 400,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          });
        }

        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        stagingDir = getImportsStagingDir(timestamp);

        const storedPaths: string[] = [];
        const skipped: string[] = [];

        for (let idx = 0; idx < fileEntries.length; idx++) {
          const entry = fileEntries[idx];
          if (!(entry instanceof File)) {
            skipped.push(`non-file-${idx}`);
            continue;
          }

          const providedName = entry.name || `upload-${idx}`;
          const relativePath = sanitiseRelativePath(providedName);
          const destination = path.join(stagingDir, relativePath);

          await writeUploadedFile(destination, entry);
          storedPaths.push(destination);
        }

        if (storedPaths.length === 0) {
          return new Response(JSON.stringify({ error: 'Uploaded files could not be processed.', skipped }), {
            status: 400,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          });
        }

        console.log('Bulk import starting', {
          stagingDir,
          storedCount: storedPaths.length,
          autoApprove,
        });

        const summary = await bulkImportStatements({
          inputPaths: storedPaths,
          autoApprove,
        });

        return new Response(
          JSON.stringify({
            stagingDir,
            storedPaths,
            skipped,
            summary,
          }),
          {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
              ...corsHeaders,
            },
          }
        );
      } catch (error: any) {
        console.error('Bulk import error:', error);
        if (stagingDir) {
          await fs.rm(stagingDir, { recursive: true, force: true }).catch(() => {
            // ignore cleanup failure
          });
        }
        return new Response(JSON.stringify({
          error: 'Bulk import failed.',
          detail: error?.message ?? String(error),
        }), {
          status: 500,
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        });
      }
    }

    if (url.pathname.startsWith('/client/') && url.pathname.endsWith('.css')) {
      const filePath = `.${url.pathname}`;
      const file = Bun.file(filePath);

      if (await file.exists()) {
        try {
          const cssContent = await file.text();

          const postcss = require('postcss');
          const tailwindcss = require('@tailwindcss/postcss');
          const autoprefixer = require('autoprefixer');

          const result = await postcss([
            tailwindcss(),
            autoprefixer,
          ]).process(cssContent, {
            from: filePath,
            to: undefined
          });

          return new Response(result.css, {
            headers: {
              'Content-Type': 'text/css',
            },
          });
        } catch (error) {
          console.error('CSS processing error:', error);
          return new Response('CSS processing failed', { status: 500 });
        }
      }
    }

    if (url.pathname.startsWith('/client/') && (url.pathname.endsWith('.tsx') || url.pathname.endsWith('.ts'))) {
      const filePath = `.${url.pathname}`;
      const file = Bun.file(filePath);

      if (await file.exists()) {
        try {
          const transpiled = await Bun.build({
            entrypoints: [filePath],
            target: 'browser',
            format: 'esm',
          });

          if (transpiled.success) {
            const jsCode = await transpiled.outputs[0].text();
            return new Response(jsCode, {
              headers: {
                'Content-Type': 'application/javascript',
              },
            });
          }
        } catch (error) {
          console.error('Transpilation error:', error);
          return new Response('Transpilation failed', { status: 500 });
        }
      }
    }

    // Serve other static assets under /client/ (e.g., .yaml, .json)
    if (url.pathname.startsWith('/client/')) {
      const filePath = `.${url.pathname}`;
      const file = Bun.file(filePath);
      if (await file.exists()) {
        let contentType = 'text/plain';
        if (url.pathname.endsWith('.json')) contentType = 'application/json';
        else if (url.pathname.endsWith('.yaml') || url.pathname.endsWith('.yml')) contentType = 'text/yaml';
        else if (url.pathname.endsWith('.svg')) contentType = 'image/svg+xml';
        else if (url.pathname.endsWith('.png')) contentType = 'image/png';
        return new Response(file, { headers: { 'Content-Type': contentType } });
      }
    }

    if (url.pathname === '/api/chat' && req.method === 'POST') {
      return new Response(JSON.stringify({
        error: 'Please use WebSocket connection at /ws for chat'
      }), {
        status: 400,
        headers: {
          'Content-Type': 'application/json',
          ...corsHeaders,
        },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
});

console.log(`Server running at http://localhost:${server.port}`);
console.log('WebSocket endpoint available at ws://localhost:3000/ws');
console.log('Visit http://localhost:3000 to view the fin-agent interface');
