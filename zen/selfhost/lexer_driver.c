/*
 * TASK-902 driver for the self-hosted Zen lexer.
 *
 * Reads a source file into memory, calls the freestanding Zen object and prints
 * the eight counters as `key=value` on one line. Build example:
 *
 *   zen build zen/selfhost/lexer.zen --target x86_64-unknown-none --emit obj -o lexer.o
 *   cc -std=c11 -O2 -fno-pie -no-pie zen/selfhost/lexer_driver.c lexer.o -o lexer_driver
 *   ./lexer_driver zen/examples/hello.zen
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

void zen_lex_report(uint64_t source, uint64_t length, uint64_t out);

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: %s <file>\n", argc > 0 ? argv[0] : "lexer_driver");
        return 2;
    }

    FILE *file = fopen(argv[1], "rb");
    if (file == NULL) {
        fprintf(stderr, "lexer_driver: cannot open %s\n", argv[1]);
        return 2;
    }
    if (fseek(file, 0, SEEK_END) != 0) {
        fprintf(stderr, "lexer_driver: cannot seek %s\n", argv[1]);
        fclose(file);
        return 2;
    }
    long size = ftell(file);
    if (size < 0) {
        fprintf(stderr, "lexer_driver: cannot size %s\n", argv[1]);
        fclose(file);
        return 2;
    }
    rewind(file);

    size_t capacity = (size_t)size + 1;
    unsigned char *buffer = (unsigned char *)malloc(capacity);
    if (buffer == NULL) {
        fprintf(stderr, "lexer_driver: out of memory\n");
        fclose(file);
        return 2;
    }
    size_t got = fread(buffer, 1, (size_t)size, file);
    fclose(file);
    if (got != (size_t)size) {
        fprintf(stderr, "lexer_driver: short read on %s\n", argv[1]);
        free(buffer);
        return 2;
    }
    buffer[size] = 0;

    uint64_t counters[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    zen_lex_report((uint64_t)(uintptr_t)buffer, (uint64_t)got,
                   (uint64_t)(uintptr_t)counters);

    printf("tokens=%" PRIu64 " idents=%" PRIu64 " numbers=%" PRIu64
           " strings=%" PRIu64 " keywords=%" PRIu64 " punct=%" PRIu64
           " errors=%" PRIu64 " bytes=%" PRIu64 "\n",
           counters[0], counters[1], counters[2], counters[3], counters[4],
           counters[5], counters[6], counters[7]);

    free(buffer);
    return 0;
}
