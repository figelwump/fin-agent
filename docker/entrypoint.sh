#!/bin/sh
set -e

echo "=== fin-agent entrypoint ==="

# Data directory (persistent disk mount point on Render)
DATA_DIR="${FINAGENT_DATA_DIR:-/var/data}"

# Ensure data directories exist with correct permissions
mkdir -p "$DATA_DIR/imports"
chmod -R 755 "$DATA_DIR"

# Set environment variables for persistent storage
export FINAGENT_DATABASE_PATH="${FINAGENT_DATABASE_PATH:-$DATA_DIR/data.db}"

# Create symlinks from home directory for CLI compatibility
# (fin-cli tools reference ~/.finagent by default)
mkdir -p ~/.finagent
if [ ! -L ~/.finagent/data.db ] && [ -n "$FINAGENT_DATABASE_PATH" ]; then
    ln -sf "$FINAGENT_DATABASE_PATH" ~/.finagent/data.db 2>/dev/null || true
fi

# Initialize database if it doesn't exist
if [ ! -f "$FINAGENT_DATABASE_PATH" ]; then
    echo "Initializing database at $FINAGENT_DATABASE_PATH..."
    # Run a simple fin-query command to trigger database creation
    fin-query schema --table transactions 2>/dev/null || echo "Database will be created on first use"
fi

echo "Database path: $FINAGENT_DATABASE_PATH"
echo "Starting server..."

# Hand off to the main container command
exec "$@"
