"""Structured outputs for the LLM stages."""

from pydantic import BaseModel, Field


class Issue(BaseModel):
    severity: str = Field(description="One of: critical, high, medium, low.")
    line: int = Field(description="Line number in the submitted code (0 if general).")
    category: str = Field(description="e.g. security, correctness, error-handling, maintainability, style.")
    problem: str = Field(description="What is wrong and why it matters, in one or two sentences.")
    suggestion: str = Field(description="Concrete way to fix it.")


class Review(BaseModel):
    summary: str = Field(description="2-3 sentence overall assessment.")
    verdict: str = Field(description="One of: approve, approve_with_comments, request_changes.")
    quality_score: int = Field(description="Overall quality from 1 (poor) to 10 (excellent).")
    issues: list[Issue] = Field(description="Real problems, most severe first. Merge duplicates.")
    positives: list[str] = Field(description="Things the code does well (may be empty).")


class FixedCode(BaseModel):
    code: str = Field(description="The COMPLETE corrected Python source file, not a diff.")
    changes: list[str] = Field(description="Short bullet list of what was changed and why.")
