#!/bin/bash
# Build script for Render
# Runs unit tests before deployment
# Exits with code 1 if tests fail, blocking the build

set -e  # Exit on first error

echo "================================"
echo "🧪 Running Pre-Deployment Tests"
echo "================================"
echo ""

# Run unit tests
python3 run_tests.py

if [ $? -ne 0 ]; then
    echo ""
    echo "================================"
    echo "❌ BUILD FAILED: Tests did not pass"
    echo "================================"
    exit 1
fi

echo ""
echo "================================"
echo "✅ All tests passed - build approved"
echo "================================"
