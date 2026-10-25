"""Structured outputs passed between the pipeline stages."""

from pydantic import BaseModel, Field


class ICP(BaseModel):
    """Ideal customer profile extracted from the user's request."""

    product_offering: str = Field(description="What the user sells or offers, in one sentence.")
    target_industry: str = Field(description="Industry of the companies to find.")
    region: str = Field(description="Country or region of the companies to find.")
    num_leads: int = Field(description="How many leads the user wants (default 5, max 10).")
    buying_signals: list[str] = Field(
        description="Observable events suggesting a company needs the offering, e.g. 'raised funding', 'hiring for X'."
    )


class ResearchPlan(BaseModel):
    queries: list[str] = Field(description="4 to 6 distinct web search queries covering different angles.")


class Lead(BaseModel):
    company: str
    website: str = Field(description="Company website or best known URL; empty if unknown.")
    summary: str = Field(description="What the company does, in one sentence.")
    why_fit: str = Field(description="Why this company matches the ICP, citing concrete evidence.")
    signals: list[str] = Field(description="Specific buying signals observed, each with a rough date if known.")
    score: int = Field(description="Fit score 1-10 (10 = strongest fit and clearest buying signals).")
    sources: list[str] = Field(description="URLs or publication names that support the claims.")


class LeadList(BaseModel):
    leads: list[Lead]
