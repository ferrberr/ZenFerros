/* TASK-902C: driver C del parser con AST Zen freestanding.
 *
 * Uso: ast_driver EXPR_FILE
 * Lee una expresion por linea (maximo 512 bytes utiles), llama a
 * zen_ast_eval y escribe "status=<n> value=<n> nodes=<n> ast=<n>" por linea.
 * La libc vive solo en este adaptador de proceso Linux; el objeto Zen no
 * importa simbolos externos.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern uint64_t zen_ast_eval(uint64_t text, uint64_t length, uint64_t out);

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
    /* 512 bytes utiles + '\n' + NUL. */
    char line[514];
    uint64_t result[4];
    int status = 0;
    while (fgets(line, (int)sizeof line, file) != NULL) {
        size_t length = strlen(line);
        while (length > 0 && (line[length - 1] == '\n' || line[length - 1] == '\r')) {
            line[--length] = '\0';
        }
        result[0] = 0;
        result[1] = 0;
        result[2] = 0;
        result[3] = 0;
        zen_ast_eval((uint64_t)(uintptr_t)line, (uint64_t)length,
                     (uint64_t)(uintptr_t)result);
        if (printf("status=%llu value=%llu nodes=%llu ast=%llu\n",
                   (unsigned long long)result[0],
                   (unsigned long long)result[1],
                   (unsigned long long)result[2],
                   (unsigned long long)result[3]) < 0) {
            status = 1;
            break;
        }
    }
    if (status == 0 && ferror(file)) {
        status = 1;
    }
    fclose(file);
    return status;
}
