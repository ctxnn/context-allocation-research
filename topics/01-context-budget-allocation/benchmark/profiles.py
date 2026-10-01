"""Model context profiles.

Limits and reserves are experimental stand-ins for model-specific serving
config. They are not taken from a production table.
"""

from __future__ import annotations

from benchmark.schema import ModelProfile

# output_reserve: tokens held back for the model completion
# tool_reserve: extra headroom for a tool-call payload on this turn
PROFILES: dict[str, ModelProfile] = {
    "32k": ModelProfile("32k", 32_768, output_reserve=4_096, tool_reserve=512, cost_per_mtok_input=0.15),
    "64k": ModelProfile("64k", 65_536, output_reserve=8_192, tool_reserve=1_024, cost_per_mtok_input=0.15),
    "128k": ModelProfile("128k", 131_072, output_reserve=8_192, tool_reserve=2_048, cost_per_mtok_input=0.15),
    "256k": ModelProfile("256k", 262_144, output_reserve=16_384, tool_reserve=2_048, cost_per_mtok_input=0.15),
}


def input_budget(profile: ModelProfile) -> int:
    return profile.input_budget
