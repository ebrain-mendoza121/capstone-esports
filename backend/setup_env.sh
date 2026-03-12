#!/bin/bash

echo "=== Supabase Connection String Setup ==="
echo ""
echo "1. Go to https://supabase.com/dashboard"
echo "2. Select your project"
echo "3. Go to Settings → Database"
echo "4. Find 'Connection String' section"
echo "5. Select 'Session pooler' mode"
echo "6. Copy the connection string"
echo ""
echo "It should look like:"
echo "postgresql://postgres.xxxxx:password@aws-0-region.pooler.supabase.com:5432/postgres"
echo ""
read -p "Paste your Supabase connection string here: " SUPABASE_URL

# Remove any trailing whitespace
SUPABASE_URL=$(echo "$SUPABASE_URL" | xargs)

# Check if URL is valid
if [[ ! $SUPABASE_URL =~ ^postgresql:// ]]; then
    echo "Error: Invalid connection string. It should start with 'postgresql://'"
    exit 1
fi

# Create DATABASE_URL (add +psycopg)
DATABASE_URL="${SUPABASE_URL/postgresql:\/\//postgresql+psycopg://}"

# Add sslmode if not present
if [[ ! $SUPABASE_URL =~ sslmode ]]; then
    SUPABASE_URL="${SUPABASE_URL}?sslmode=require"
    DATABASE_URL="${DATABASE_URL}?sslmode=require"
fi

echo ""
echo "=== Riot API Key Setup ==="
echo ""
echo "1. Go to https://developer.riotgames.com"
echo "2. Sign in with your Riot account"
echo "3. Copy your Development API Key"
echo ""
read -p "Paste your Riot API key here: " RIOT_KEY

# Create .env file
cat > .env << EOF
# Database URLs
DATABASE_URL=$DATABASE_URL
PRISMA_DATABASE_URL=$SUPABASE_URL

# CORS Origins
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Riot API Key
RIOT_API_KEY=$RIOT_KEY
EOF

echo ""
echo "✅ .env file created successfully!"
echo ""
echo "Next steps:"
echo "1. Run: npm run prisma:migrate:deploy"
echo "2. Run: python -m uvicorn app.main:app --reload"
echo ""
