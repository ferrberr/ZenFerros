// Benchmark: C++17 reference for volatile in-place heapsort over 500k u32.
#include <cstdint>
#include <cstdio>
#include <cstdlib>

static std::uint32_t load(const volatile std::uint32_t *array, std::uint64_t index) {
    return array[index];
}
static void store(volatile std::uint32_t *array, std::uint64_t index, std::uint32_t value) {
    array[index] = value;
}
static void sift(volatile std::uint32_t *array, std::uint64_t start, std::uint64_t end) {
    std::uint64_t root = start;
    while (root * 2 + 1 <= end) {
        std::uint64_t child = root * 2 + 1;
        if (child + 1 <= end && load(array, child) < load(array, child + 1)) {
            child += 1;
        }
        if (load(array, root) < load(array, child)) {
            std::uint32_t left = load(array, root);
            std::uint32_t right = load(array, child);
            store(array, root, right);
            store(array, child, left);
            root = child;
        } else {
            return;
        }
    }
}

int main() {
    const std::uint64_t count = 500000u;
    volatile std::uint32_t *array =
        static_cast<volatile std::uint32_t *>(std::malloc(static_cast<std::size_t>(count) * 4u));
    if (!array) return 2;
    std::uint64_t state = 987654321u;
    for (std::uint64_t i = 0; i < count; i++) {
        state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
        store(array, i, static_cast<std::uint32_t>(state >> 33));
    }
    if (count > 1) {
        for (std::uint64_t start = count / 2; start > 0; ) {
            start -= 1;
            sift(array, start, count - 1);
        }
        for (std::uint64_t end = count - 1; end > 0; ) {
            std::uint32_t first = load(array, 0);
            std::uint32_t last = load(array, end);
            store(array, 0, last);
            store(array, end, first);
            end -= 1;
            sift(array, 0, end);
        }
    }
    std::uint64_t checksum = 0;
    for (std::uint64_t i = 0; i < count; i++) {
        checksum = checksum * 31 + load(array, i);
    }
    std::free(const_cast<std::uint32_t *>(array));
    std::printf("%llu\n", static_cast<unsigned long long>(checksum));
    return 0;
}
