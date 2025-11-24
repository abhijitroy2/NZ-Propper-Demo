#!/bin/sh
# Replace BACKEND_URL placeholder in nginx config
# Default to http://localhost:8000 if not set
BACKEND_URL=${BACKEND_URL:-http://localhost:8000}

# Validate BACKEND_URL is set and not empty
if [ -z "$BACKEND_URL" ]; then
    echo "ERROR: BACKEND_URL environment variable is not set!"
    exit 1
fi

# Ensure BACKEND_URL doesn't have trailing slash for proxy_pass
BACKEND_URL=$(echo "$BACKEND_URL" | sed 's|/$||')

# Use sed to replace the ${BACKEND_URL} placeholder
# Escape special characters in the URL for sed
ESCAPED_BACKEND_URL=$(echo "$BACKEND_URL" | sed 's/[[\.*^$()+?{|]/\\&/g')
sed -i "s|\${BACKEND_URL}|$ESCAPED_BACKEND_URL|g" /etc/nginx/conf.d/default.conf

# Test nginx configuration
nginx -t || {
    echo "ERROR: Nginx configuration test failed!"
    echo "BACKEND_URL was: $BACKEND_URL"
    cat /etc/nginx/conf.d/default.conf
    exit 1
}

# Start nginx
exec nginx -g 'daemon off;'

