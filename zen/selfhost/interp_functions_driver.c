/*
 * TASK-902F: driver C del interprete selfhost con funciones escrito en Zen.
 *
 * Uso: interp_functions_driver PROGRAMA.zen
 *
 * Lee el fichero completo (una invocacion = un programa), llama a
 * zen_interp_fns y escribe exactamente una linea:
 *
 *   status=<n> statements=<n> hash=<n> bytes=<n>
 *
 * Exit status: 0 si el driver pudo leer y llamar al interprete (incluidos
 * errores de sintaxis/ejecucion del lenguaje interpretado), 2 en errores de
 * uso/IO. La libc vive solo en este adaptador; el objeto Zen no importa
 * simbolos externos.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern uint64_t zen_interp_fns(uint64_t source, uint64_t length, uint64_t out);

static int read_whole_file(const char *path, unsigned char **buffer,
                           uint64_t *length) {
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        fprintf(stderr, "interp_functions_driver: cannot open %s\n", path);
        return 0;
    }
    if (fseek(file, 0, SEEK_END) != 0) {
        fprintf(stderr, "interp_functions_driver: cannot seek %s\n", path);
        fclose(file);
        return 0;
    }
    long size = ftell(file);
    if (size < 0) {
        fprintf(stderr, "interp_functions_driver: cannot size %s\n", path);
        fclose(file);
        return 0;
    }
    rewind(file);

    size_t capacity = (size_t)size + 1u;
    unsigned char *data = (unsigned char *)malloc(capacity);
    if (data == NULL) {
        fprintf(stderr, "interp_functions_driver: out of memory\n");
        fclose(file);
        return 0;
    }
    size_t got = fread(data, 1, (size_t)size, file);
    fclose(file);
    if (got != (size_t)size) {
        fprintf(stderr, "interp_functions_driver: short read on %s\n", path);
        free(data);
        return 0;
    }
    data[size] = 0;
    *buffer = data;
    *length = (uint64_t)got;
    return 1;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: %s PROGRAM_FILE\n", argv[0]);
        return 2;
    }
    unsigned char *data = NULL;
    uint64_t length = 0;
    if (!read_whole_file(argv[1], &data, &length)) {
        return 2;
    }
    uint64_t out[4] = {0, 0, 0, 0};
    zen_interp_fns((uint64_t)(uintptr_t)data, length, (uint64_t)(uintptr_t)out);
    int rc = 0;
    if (printf("status=%llu statements=%llu hash=%llu bytes=%llu\n",
               (unsigned long long)out[0],
               (unsigned long long)out[1],
               (unsigned long long)out[2],
               (unsigned long long)out[3]) < 0) {
        rc = 1;
    }
    free(data);
    return rc;
}
