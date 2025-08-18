#!/bin/bash
# Increase Node.js heap memory for TypeScript checking
NODE_OPTIONS="--max-old-space-size=4096" npx vue-tsc --noEmit
