/*
 * TASK-902D driver for the self-hosted materializing Zen lexer.
 *
 * Reads a source file, calls `zen_lex_tokens` (16-byte records: kind, start,
 * end, value) and prints one line per token:
 *
 *   kind=<n> start=<n> end=<n> value=<hex>
 *
 * The default capacity is 8192 tokens (vfs.zen had ~3393 when this test was
 * written); an optional second argument overrides it. The token count returned
 * by Zen is reported on
 * stderr as `tokens=<n>`. If Zen returns 0xFFFFFFFF (capacity exceeded or
 * unrecoverable lexical error) the driver prints `error=0xffffffff` on stderr
 * and exits 3 without a partial token listing.
 *
 * Build example:
 *   zen build zen/selfhost/lexer_tokens.zen --target x86_64-unknown-none \
 *       --emit obj -o lexer_tokens.o
 *   cc -std=c11 -O2 -fno-pie -no-pie zen/selfhost/lexer_tokens_driver.c \
 *       lexer_tokens.o -o lexer_tokens_driver
 *   ./lexer_tokens_driver zen/examples/hello.zen
 *
 * Exit status: 0 ok, 2 usage/IO error, 3 capacity/lexical error.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

uint64_t zen_lex_tokens(uint64_t source, uint64_t length, uint64_t out,
                        uint64_t max_tokens);

#define DEFAULT_MAX_TOKENS 8192u
#define HARD_MAX_TOKENS 1048576u
#define RECORD_BYTES 16u

static int read_whole_file(const char *path, unsigned char **buffer,
                           uint64_t *length) {
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        fprintf(stderr, "lexer_tokens_driver: cannot open %s\n", path);
        return 0;
    }
    if (fseek(file, 0, SEEK_END) != 0) {
        fprintf(stderr, "lexer_tokens_driver: cannot seek %s\n", path);
        fclose(file);
        return 0;
    }
    long size = ftell(file);
    if (size < 0) {
        fprintf(stderr, "lexer_tokens_driver: cannot size %s\n", path);
        fclose(file);
        return 0;
    }
    rewind(file);

    size_t capacity = (size_t)size + 1u;
    unsigned char *data = (unsigned char *)malloc(capacity);
    if (data == NULL) {
        fprintf(stderr, "lexer_tokens_driver: out of memory\n");
        fclose(file);
        return 0;
    }
    size_t got = fread(data, 1, (size_t)size, file);
    fclose(file);
    if (got != (size_t)size) {
        fprintf(stderr, "lexer_tokens_driver: short read on %s\n", path);
        free(data);
        return 0;
    }
    data[size] = 0;
    *buffer = data;
    *length = (uint64_t)got;
    return 1;
}

static uint32_t record_u32(const unsigned char *records, uint64_t index,
                           unsigned offset) {
    uint32_t value = 0;
    memcpy(&value, records + (size_t)index * RECORD_BYTES + offset, sizeof value);
    return value;
}

int main(int argc, char **argv) {
    if (argc < 2 || argc > 3) {
        fprintf(stderr, "usage: %s <file> [max_tokens]\n",
                argc > 0 ? argv[0] : "lexer_tokens_driver");
        return 2;
    }

    uint64_t max_tokens = DEFAULT_MAX_TOKENS;
    if (argc == 3) {
        char *end = NULL;
        unsigned long long parsed = strtoull(argv[2], &end, 10);
        if (end == argv[2] || *end != '\0' || parsed == 0 ||
            parsed > HARD_MAX_TOKENS) {
            fprintf(stderr, "lexer_tokens_driver: invalid max_tokens %s\n",
                    argv[2]);
            return 2;
        }
        max_tokens = (uint64_t)parsed;
    }

    unsigned char *source = NULL;
    uint64_t length = 0;
    if (!read_whole_file(argv[1], &source, &length)) {
        return 2;
    }

    uint64_t capacity = max_tokens * RECORD_BYTES;
    unsigned char *records = (unsigned char *)calloc((size_t)max_tokens,
                                                     RECORD_BYTES);
    if (records == NULL) {
        fprintf(stderr, "lexer_tokens_driver: out of memory\n");
        free(source);
        return 2;
    }

    uint64_t count = zen_lex_tokens((uint64_t)(uintptr_t)source, length,
                                    (uint64_t)(uintptr_t)records, max_tokens);
    free(source);

    if (count == UINT64_C(0xFFFFFFFF)) {
        fprintf(stderr, "error=0xffffffff\n");
        free(records);
        return 3;
    }
    if (count > max_tokens) {
        fprintf(stderr, "lexer_tokens_driver: inconsistent token count %" PRIu64
                        " (max %" PRIu64 ", %" PRIu64 " bytes)\n",
                count, max_tokens, capacity);
        free(records);
        return 2;
    }

    for (uint64_t i = 0; i < count; i++) {
        uint32_t kind = record_u32(records, i, 0);
        uint32_t start = record_u32(records, i, 4);
        uint32_t end = record_u32(records, i, 8);
        uint32_t value = record_u32(records, i, 12);
        printf("kind=%" PRIu32 " start=%" PRIu32 " end=%" PRIu32
               " value=0x%08" PRIx32 "\n",
               kind, start, end, value);
    }
    fprintf(stderr, "tokens=%" PRIu64 "\n", count);

    free(records);
    return 0;
}
