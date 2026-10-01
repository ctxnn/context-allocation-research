from benchmark.allocators.fixed_quota import FixedQuotaAllocator
from benchmark.allocators.recency import RecencyAllocator
from benchmark.allocators.utility import UtilityAllocator
from benchmark.allocators.waterfill import WaterfillAllocator

ALLOCATORS = {
    "fixed_quota": FixedQuotaAllocator,
    "waterfill": WaterfillAllocator,
    "utility": UtilityAllocator,
    "recency": RecencyAllocator,
}


def get_allocators() -> list:
    return [cls() for cls in ALLOCATORS.values()]
