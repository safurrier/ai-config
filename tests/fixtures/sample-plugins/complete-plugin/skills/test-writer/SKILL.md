---
name: test-writer
description: Generate comprehensive test cases for code. Use when asked to write tests, add test coverage, or create test files.
allowed-tools: Read, Write, Bash
---

## Test Writer Instructions

Generate tests following these principles:

### Test Structure
- Use the project's existing test framework (pytest, jest, etc.)
- Follow existing naming conventions
- Group related tests in classes/describes

### Coverage Goals
1. Happy path - normal expected behavior
2. Edge cases - boundary conditions, empty inputs
3. Error cases - invalid inputs, failure modes
4. Integration points - external dependencies

### Best Practices
- One assertion per test (when reasonable)
- Descriptive test names
- Use fixtures for shared setup
- Mock external dependencies
- Avoid test interdependence

## Template

```python
def test_<function>_<scenario>_<expected_result>():
    # Arrange
    ...
    # Act
    ...
    # Assert
    ...
```
