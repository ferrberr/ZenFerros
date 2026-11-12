/* TASK-925: libc plumbing only. Compiler/CLI policy lives in cli.zen. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern uint64_t zen_selfhost_cli(uint64_t argc, uint64_t argv);
uint64_t sh_alloc(uint64_t size) { return (uint64_t)(uintptr_t)malloc((size_t)size); }
void sh_free(uint64_t address) { free((void *)(uintptr_t)address); }
uint64_t sh_read(uint64_t path, uint64_t buffer, uint64_t capacity) {
    FILE *file = fopen((const char *)(uintptr_t)path, "rb");
    if (!file) return UINT64_MAX;
    size_t size = fread((void *)(uintptr_t)buffer, 1, (size_t)capacity, file);
    int failed = ferror(file);
    /* A byte beyond capacity is rejected; exact capacity remains valid. */
    if (!failed && size == capacity && fgetc(file) != EOF) failed = 1;
    if (fclose(file) != 0) failed = 1;
    return failed ? UINT64_MAX : (uint64_t)size;
}
uint64_t sh_write(uint64_t buffer, uint64_t length) {
    size_t wrote = fwrite((const void *)(uintptr_t)buffer, 1, (size_t)length, stdout);
    return wrote != length || fflush(stdout) != 0;
}
void sh_error(uint64_t code) {
    const char *message = "I/O or allocation error";
    if (code == 2) message = "usage: zen-selfhost PROGRAM.zen (or I/O/allocation error)";
    if (code == 4) message = "compiler capacity exceeded";
    if (code == 5) message = "syntax, lexical error or unsupported subset";
    if (code == 6) message = "type, name or mutability error";
    fprintf(stderr, "zen-selfhost: %s\n", message);
}
int main(int argc, char **argv) {
    return (int)zen_selfhost_cli((uint64_t)argc, (uint64_t)(uintptr_t)argv);
}
