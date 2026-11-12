// Benchmark reference: in-place heapsort over 500k u32 with volatile access
// (same as zen/sort.zen).
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static uint32_t load(const volatile uint32_t *array, uint64_t index) {
    return array[index];
}
static void store(volatile uint32_t *array, uint64_t index, uint32_t value) {
    array[index] = value;
}
static void sift(volatile uint32_t *array, uint64_t start, uint64_t end) {
    uint64_t root = start;
    while (root * 2 + 1 <= end) {
        uint64_t child = root * 2 + 1;
        if (child + 1 <= end && load(array, child) < load(array, child + 1)) {
            child += 1;
        }
        if (load(array, root) < load(array, child)) {
            uint32_t left = load(array, root);
            uint32_t right = load(array, child);
            store(array, root, right);
            store(array, child, left);
            root = child;
        } else {
            return;
        }
    }
}

int main(void) {
    const uint64_t count = 500000u;
    volatile uint32_t *array = malloc((size_t)count * 4u);
    if (!array) return 2;
    uint64_t state = 987654321u;
    for (uint64_t i = 0; i < count; i++) {
        state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
        store(array, i, (uint32_t)(state >> 33));
    }
    if (count > 1) {
        for (uint64_t start = count / 2; start > 0; ) {
            start -= 1;
            sift(array, start, count - 1);
        }
        for (uint64_t end = count - 1; end > 0; ) {
            uint32_t first = load(array, 0);
            uint32_t last = load(array, end);
            store(array, 0, last);
            store(array, end, first);
            end -= 1;
            sift(array, 0, end);
        }
    }
    uint64_t checksum = 0;
    for (uint64_t i = 0; i < count; i++) {
        checksum = checksum * 31 + load(array, i);
    }
    free((void *)array);
    printf("%llu\n", (unsigned long long)checksum);
    return 0;
}
