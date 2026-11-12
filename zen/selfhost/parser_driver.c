/* TASK-902B: driver C del evaluador Zen freestanding.
 *
 * Uso: parser_driver EXPR_FILE
 * Lee una expresion por linea (maximo 256 bytes utiles), llama a zen_eval y
 * escribe "status=<n> value=<n>" por linea. No usa la libc dentro del codigo
 * Zen: solo este adaptador de proceso Linux.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern uint64_t zen_eval(uint64_t text, uint64_t length, uint64_t out);

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: %s EXPR_FILE\n", argv[0]);
        return 2;
    }
    FILE *file = fopen(argv[1], "r");
    if (file == NULL) {
        perror(argv[1]);
        return 2;
    }
    char line[512];
    uint64_t result[2];
    while (fgets(line, (int)sizeof line, file) != NULL) {
        size_t length = strlen(line);
        while (length > 0 && (line[length - 1] == '\n' || line[length - 1] == '\r')) {
            line[--length] = '\0';
        }
        result[0] = 0;
        result[1] = 0;
        zen_eval((uint64_t)(uintptr_t)line, (uint64_t)length,
                 (uint64_t)(uintptr_t)result);
        if (printf("status=%llu value=%llu\n",
                   (unsigned long long)result[0],
                   (unsigned long long)result[1]) < 0) {
            fclose(file);
            return 1;
        }
    }
    if (ferror(file)) {
        fclose(file);
        return 1;
    }
    fclose(file);
    return 0;
}
