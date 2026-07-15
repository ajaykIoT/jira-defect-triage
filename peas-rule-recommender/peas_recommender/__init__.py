"""PEaS Rule Recommendation Engine.

Analyzes manual repair cases from the GPE new_journal table, clusters them,
and recommends new or updated PEaS enrichment rules with confidence scoring.
Operator accept/reject decisions feed back into the model.
"""

__version__ = "0.1.0"
