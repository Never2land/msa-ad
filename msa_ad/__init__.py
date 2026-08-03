"""msa-ad: Measurement System Analysis for Automated-Driving Validation.

Transfers two production-metrology practices onto automated-driving
validation benches:

1. **Bench characterisation** - how much of an observed scenario verdict
   originates in the apparatus rather than in the system under test
   (:mod:`msa_ad.gage_rr`).
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
)
from .seed_faults import (
    CoverageClaimComparison,
    FaultCatalogueError,
    SeededFaultResult,
    analyse_seeded_faults,
    compare_claimed_coverage,
)

__version__ = "0.1.0"
__author__ = "Linlin Wang"

__all__ = [
    "__version__",
    "AttributeAgreementResult",
    "BiasLinearityResult",
    "BinaryDataError",
    "CoverageClaimComparison",
    "FaultCatalogueError",
    "GageRRResult",
    "SeededFaultResult",
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
    "wilson_interval",
]
