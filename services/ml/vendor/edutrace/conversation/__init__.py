"""Post-flag support: a structured supportive conversation, not a psychometric test.

Read ``protocol.py``'s module docstring before changing anything here. The
design deliberately does not implement a teacher-administered psychometric
assessment, for licensing, scope-of-practice, norming and safeguarding reasons
that are all set out there.
"""

from .protocol import PROMPTS, ConversationGuide, Domain, Finding, NeedsProfile, Prompt
from .safeguarding import Category, EscalationRecord, Referral, escalate

__all__ = [
    "PROMPTS", "ConversationGuide", "Domain", "Finding", "NeedsProfile", "Prompt",
    "Category", "EscalationRecord", "Referral", "escalate",
]
