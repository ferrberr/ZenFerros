// Benchmark reference: Collatz step count over 1..=500k (same as zen/collatz.zen).
#include <stdint.h>
#include <stdio.h>

static uint64_t steps(uint64_t n) {
    uint64_t value = n;
    uint64_t count = 0;
    while (value != 1) {
        if (value % 2 == 0) {
            value = value / 2;
        } else {
            value = value * 3 + 1;
        }
        count += 1;
    }
    return count;
}

int main(void) {
    uint64_t total = 0;
    for (uint64_t n = 1; n <= 500000; n++) {
        total += steps(n);
    }
    printf("%llu\n", (unsigned long long)total);
    return 0;
}
