"""msa-ad: Measurement System Analysis for Automated-Driving Validation.

Transfers two production-metrology practices onto automated-driving
validation benches:

1. **Bench characterisation** - how much of an observed scenario verdict
   originates in the apparatus rather than in the system under test
   (:mod:`msa_ad.gage_rr`), optionally under a two-tier fixed-seed /
   varied-seed design that separates apparatus error from deliberately
   injected scenario stochasticity (:mod:`msa_ad.two_tier`).
2. **Coverage-claim verification** - seeded known faults run through the
   production campaign, yielding a measured detection rate reportable
   alongside any coverage claim (:mod:`msa_ad.seed_faults`).

This is a proposed method and a reference implementation. It is not a
standard and has not been validated against industrial data. See the README
for status and limitations.
"""

from .gage_rr import (
    AttributeAgreementResult,
    BiasLinearityResult,
    BinaryDataError,
    GageRRResult,
    UnbalancedDesignError,
    attribute_agreement,
    bias_linearity_study,
    cohen_kappa,
    fleiss_kappa,
    gage_rr_anova,
    looks_binary,
    wilson_interval,
)
from .report import (
    render_attribute_report,
    render_bias_report,
    render_coverage_claim_report,
    render_gage_rr_report,
    render_seeded_fault_report,
    render_two_tier_report,
)
from .seed_faults import (
    CoverageClaimComparison,
    FaultCatalogueError,
    SeededFaultResult,
    analyse_seeded_faults,
    compare_claimed_coverage,
)
from .two_tier import (
    TIER_FIXED_SEED,
    TIER_VARIED_SEED,
    MissingTierError,
    TierMismatchError,
    TwoTierResult,
    two_tier_gage_rr,
    two_tier_gage_rr_from_frames,
)

__version__ = "0.1.1"
__author__ = "Linlin Wang"

__all__ = [
    "__version__",
    "AttributeAgreementResult",
    "BiasLinearityResult",
    "BinaryDataError",
    "CoverageClaimComparison",
    "FaultCatalogueError",
    "GageRRResult",
    "MissingTierError",
    "SeededFaultResult",
    "TIER_FIXED_SEED",
    "TIER_VARIED_SEED",
    "TierMismatchError",
    "TwoTierResult",
    "UnbalancedDesignError",
    "analyse_seeded_faults",
    "attribute_agreement",
    "bias_linearity_study",
    "cohen_kappa",
    "compare_claimed_coverage",
    "fleiss_kappa",
    "gage_rr_anova",
    "looks_binary",
    "render_attribute_report",
    "render_bias_report",
    "render_coverage_claim_report",
    "render_gage_rr_report",
    "render_seeded_fault_report",
    "render_two_tier_report",
    "two_tier_gage_rr",
    "two_tier_gage_rr_from_frames",
    "wilson_interval",
]
