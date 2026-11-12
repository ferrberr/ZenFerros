// Benchmark reference: volatile sequential byte write+read over 16 MiB
// (same as zen/mem.zen). Uses libc malloc/free and volatile accesses.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main(void) {
    const size_t size = 16777216u;
    volatile unsigned char *buffer = malloc(size);
    if (!buffer) return 2;
    uint64_t state = 12345u;
    for (size_t i = 0; i < size; i++) {
        state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
        buffer[i] = (unsigned char)(state >> 33);
    }
    uint64_t sum = 0;
    for (size_t i = 0; i < size; i++) {
        sum += buffer[i];
    }
    free((void *)buffer);
    printf("%llu\n", (unsigned long long)sum);
    return 0;
}
