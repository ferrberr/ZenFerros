// Benchmark: C++17 Collatz step count over 1..=500k.
#include <cstdint>
#include <cstdio>

static std::uint64_t steps(std::uint64_t n) {
    std::uint64_t value = n;
    std::uint64_t count = 0;
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

int main() {
    std::uint64_t total = 0;
    for (std::uint64_t n = 1; n <= 500000; n++) {
        total += steps(n);
    }
    std::printf("%llu\n", static_cast<unsigned long long>(total));
    return 0;
}
