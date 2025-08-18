#!/bin/bash

# Script untuk mengecek kualitas kode TypeScript dan ESLint
# Usage: ./check-code-quality.sh

echo "🔍 Starting Code Quality Checks..."
echo "================================="
echo ""

# Function to print colored output
print_success() {
    echo -e "\033[32m✅ $1\033[0m"
}

print_error() {
    echo -e "\033[31m❌ $1\033[0m"
}

print_warning() {
    echo -e "\033[33m⚠️ $1\033[0m"
}

print_info() {
    echo -e "\033[34mℹ️ $1\033[0m"
}

# Initialize error counter
ERRORS=0

# TypeScript Check
echo "=== TypeScript Check ==="
echo "Running: npx vue-tsc --noEmit"
if npx vue-tsc --noEmit; then
    print_success "TypeScript: No errors found"
else
    print_error "TypeScript: Errors found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Nuxt TypeScript Check
echo "=== Nuxt TypeScript Check ==="
echo "Running: npx nuxi typecheck"
if npx nuxi typecheck; then
    print_success "Nuxt TypeScript: No errors found"
else
    print_error "Nuxt TypeScript: Errors found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# ESLint Check
echo "=== ESLint Check ==="
echo "Running: npx eslint ."
if npx eslint .; then
    print_success "ESLint: No problems found"
else
    print_error "ESLint: Problems found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# ESLint with auto-fix (optional check)
echo "=== ESLint Auto-fix Check ==="
echo "Running: npx eslint . --fix"
if npx eslint . --fix; then
    print_success "ESLint Auto-fix: Completed successfully"
else
    print_warning "ESLint Auto-fix: Some issues remain"
fi
echo ""

# Summary
echo "=== Summary ==="
echo "=============="
if [ $ERRORS -eq 0 ]; then
    print_success "🎉 All code quality checks passed!"
    echo ""
    print_info "Your code is ready for production! 🚀"
    exit 0
else
    print_error "❌ Found $ERRORS issue(s) that need attention"
    echo ""
    print_info "Please fix the issues above before proceeding."
    exit 1
fi
