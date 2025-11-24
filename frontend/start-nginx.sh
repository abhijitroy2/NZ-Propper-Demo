#!/bin/sh
set -e

echo "Starting nginx startup script..."

# Get PORT from Railway (defaults to 80 if not set)
PORT=${PORT:-80}
echo "PORT environment variable: $PORT"

# Replace BACKEND_URL placeholder in nginx config
# Default to http://localhost:8000 if not set (for local testing)
BACKEND_URL=${BACKEND_URL:-http://localhost:8000}
echo "BACKEND_URL: $BACKEND_URL"

# Ensure BACKEND_URL doesn't have trailing slash for proxy_pass
BACKEND_URL=$(echo "$BACKEND_URL" | sed 's|/$||')

# Update nginx to listen on PORT env var (Railway requirement)
# Bind to all interfaces (0.0.0.0) to ensure Railway can connect
sed -i "s/listen 80;/listen $PORT;/g" /etc/nginx/conf.d/default.conf
sed -i "s/listen \[::\]:80;/listen [::]:$PORT;/g" /etc/nginx/conf.d/default.conf
echo "Updated nginx to listen on port $PORT (IPv4 and IPv6)"

# Use sed to replace the ${BACKEND_URL} placeholder
# Escape special characters in the URL for sed
ESCAPED_BACKEND_URL=$(echo "$BACKEND_URL" | sed 's/[[\.*^$()+?{|]/\\&/g')
sed -i "s|\${BACKEND_URL}|$ESCAPED_BACKEND_URL|g" /etc/nginx/conf.d/default.conf
echo "Updated nginx proxy_pass to: $BACKEND_URL"

# Test nginx configuration
echo "Testing nginx configuration..."
nginx -t || {
    echo "ERROR: Nginx configuration test failed!"
    echo "BACKEND_URL was: $BACKEND_URL"
    echo "PORT was: $PORT"
    echo "Nginx config file contents:"
    cat /etc/nginx/conf.d/default.conf
    exit 1
}

echo "Nginx configuration test passed. Starting nginx..."
# Start nginx
exec nginx -g 'daemon off;'

