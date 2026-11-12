// Benchmark: C++17 reference for volatile sequential byte write+read over 16 MiB.
#include <cstdint>
#include <cstdio>
#include <cstdlib>

int main() {
    const std::size_t size = 16777216u;
    volatile unsigned char *buffer = static_cast<volatile unsigned char *>(std::malloc(size));
    if (!buffer) return 2;
    std::uint64_t state = 12345u;
    for (std::size_t i = 0; i < size; i++) {
        state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
        buffer[i] = static_cast<unsigned char>(state >> 33);
    }
    std::uint64_t sum = 0;
    for (std::size_t i = 0; i < size; i++) {
        sum += buffer[i];
    }
    std::free(const_cast<unsigned char *>(buffer));
    std::printf("%llu\n", static_cast<unsigned long long>(sum));
    return 0;
}
