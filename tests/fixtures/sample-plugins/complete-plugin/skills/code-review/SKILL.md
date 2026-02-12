---
name: code-review
description: Review code for best practices, security issues, and style violations. Use when asked to review code, check a PR, or audit changes.
allowed-tools: Read, Grep, Glob
model: sonnet
context: fork
agent: Explore
user-invocable: true
---

## Code Review Instructions

When reviewing code, systematically check:

### 1. Security
- SQL injection vulnerabilities
- XSS vulnerabilities
- Hardcoded secrets or credentials
- Insecure dependencies

### 2. Best Practices
- Error handling coverage
- Input validation
- Resource cleanup (files, connections)
- Thread safety (if applicable)

### 3. Code Quality
- Naming conventions
- Function length and complexity
- DRY violations
- Dead code

### 4. Performance
- N+1 queries
- Unnecessary allocations
- Missing caching opportunities

## Output Format

For each finding:
1. **Location**: file:line
2. **Severity**: Critical/High/Medium/Low
3. **Issue**: Brief description
4. **Fix**: Suggested remediation
