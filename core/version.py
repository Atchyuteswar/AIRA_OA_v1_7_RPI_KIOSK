"""Single source of truth for version identifiers."""

__version__ = "1.7.0"

# Bumped whenever the meaning of stored features changes. Baseline comparison
# only mixes sessions that share the same algorithm major.minor.
ALGORITHM_VERSION = "1.4"

# Layout of the JSON records written to disk.
SCHEMA_VERSION = "1.4.0"

PRODUCT = "AIRA-OA"
DISCLAIMER = (
    "Non-diagnostic research prototype. Outputs are camera-derived movement "
    "features and a custom, non-validated symptom index; they are not a "
    "clinical diagnosis."
)
