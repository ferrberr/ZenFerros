// Benchmark reference: 64-bit wrapping LCG arithmetic (same as zen/arith.zen).
#include <stdint.h>
#include <stdio.h>

int main(void) {
    uint64_t state = UINT64_C(0x2545F4914F6CDD1D);
    uint64_t sum = 0;
    for (uint64_t i = 0; i < UINT64_C(50000000); i++) {
        state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
        sum ^= state >> 32;
    }
    printf("%llu\n", (unsigned long long)sum);
    return 0;
}
