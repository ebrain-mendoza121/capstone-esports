#!/bin/bash

echo "=== Testing Esports Analytics API ==="
echo ""

BASE_URL="http://localhost:8000"

# Test 1: Health Check
echo "1. Testing health endpoint..."
curl -s $BASE_URL/health | jq '.' || echo "Failed"
echo ""

# Test 2: Database Connection
echo "2. Testing database connection..."
curl -s $BASE_URL/health/db | jq '.' || echo "Failed"
echo ""

# Test 3: List Players
echo "3. Testing list players..."
PLAYERS=$(curl -s $BASE_URL/players/)
echo "$PLAYERS" | jq '.' || echo "$PLAYERS"
echo ""

# Get first player PUUID if available
PUUID=$(echo "$PLAYERS" | jq -r '.[0].puuid' 2>/dev/null)

if [ "$PUUID" != "null" ] && [ -n "$PUUID" ]; then
    echo "Found player with PUUID: $PUUID"
    echo ""
    
    # Test 4: Get Specific Player
    echo "4. Testing get specific player..."
    curl -s "$BASE_URL/players/$PUUID" | jq '.'
    echo ""
    
    # Test 5: Get Player Matches
    echo "5. Testing get player matches..."
    curl -s "$BASE_URL/matches/player/$PUUID?limit=5" | jq '.'
    echo ""
else
    echo "No players in database yet. Ingest a player first:"
    echo ""
    echo "curl -X POST $BASE_URL/ingest/player \\"
    echo "  -H 'Content-Type: application/json' \\"
    echo "  -d '{"
    echo "    \"gameName\": \"Doublelift\","
    echo "    \"tagLine\": \"NA1\","
    echo "    \"platform\": \"NA\","
    echo "    \"count\": 5,"
    echo "    \"queue\": 420"
    echo "  }'"
    echo ""
fi

echo "=== API Documentation ==="
echo "Visit: $BASE_URL/docs"
echo ""
