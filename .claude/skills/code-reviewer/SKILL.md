---
name: code-reviewer
description: Code review and refactoring guidelines
---

# Code Reviewer Skill

## Before Making Changes

1. **Read the code first** - Never change code you haven't read
2. **Run tests before changes** - Establish baseline
3. **Understand the context** - Why does this code exist?

## Review Checklist

### Security
- [ ] No patient data logged to console/files
- [ ] No hardcoded secrets or API keys
- [ ] Environment variables for sensitive config
- [ ] Input validation on API boundaries

### Async/Await
- [ ] All I/O operations use async/await
- [ ] No blocking calls in async functions
- [ ] Proper exception handling in async code

### Type Safety
- [ ] All function signatures have type hints
- [ ] Pydantic models for data validation
- [ ] No `Any` types without justification

### Testing
- [ ] New code has corresponding tests
- [ ] Tests mock external services (LLM, DB)
- [ ] Tests run fast (< 5 seconds for unit tests)

### API Changes
- [ ] Check for breaking changes
- [ ] Version bump if breaking
- [ ] Update API documentation

### Healthcare Specifics
- [ ] Flags have `source: "rule" | "ai"` tag
- [ ] LLM output validated against Pydantic models
- [ ] Audit logging for AI decisions

## Red Flags to Watch For

```python
# Bad: Hardcoded secret
api_key = "sk-xxx..."

# Bad: Patient data in logs
print(f"Processing patient: {patient.name}")

# Bad: Missing await
def get_patient(id):  # Should be async
    return db.query(...)

# Bad: Pydantic v1 pattern
obj = Model.parse_obj(data)  # Use model_validate()

# Bad: Direct anthropic import
from anthropic import Anthropic  # Use claude_agent_sdk
```

## After Making Changes

1. **Run tests after changes** - Compare with baseline
2. **Run linter** - `uv run ruff check .`
3. **Check type errors** - If using mypy/pyright
4. **Manual smoke test** - Does the app still work?

## Refactoring Safety

- Make small, incremental changes
- Run tests after each change
- Keep commits atomic (one logical change per commit)
- If unsure, ask before refactoring
