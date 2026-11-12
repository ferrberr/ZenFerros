// Benchmark: C++17 reference for 64-bit wrapping LCG arithmetic.
#include <cstdint>
#include <cstdio>

int main() {
    std::uint64_t state = UINT64_C(0x2545F4914F6CDD1D);
    std::uint64_t sum = 0;
    for (std::uint64_t i = 0; i < UINT64_C(50000000); i++) {
        state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
        sum ^= state >> 32;
    }
    std::printf("%llu\n", static_cast<unsigned long long>(sum));
    return 0;
}
