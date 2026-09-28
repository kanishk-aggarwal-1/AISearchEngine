# Vulture whitelist — symbols that are used dynamically and would otherwise
# be reported as dead code.
#
# Run dead-code check with:
#   python -m vulture backend/ scripts/ vulture_whitelist.py --min-confidence 80 --ignore-names cls
#
# The --ignore-names cls flag suppresses false positives from Pydantic v2
# @field_validator classmethods, where `cls` is required by Python's classmethod
# protocol even when the body doesn't reference the class directly.
