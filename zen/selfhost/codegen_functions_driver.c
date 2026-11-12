/*
 * TASK-902I: driver C del generador de codigo selfhost con funciones escrito
 * en Zen.
 *
 * Uso: codegen_functions_driver PROGRAMA.zen [SALIDA.c]
 *
 * Lee el fichero completo (una invocacion = un programa), llama a
 * zen_codegen_fns y escribe el programa C emitido en stdout o, si se da el
 * segundo argumento, en ese fichero. Exit status:
 *
 *   0  C generado y escrito correctamente
 *   2  error de uso / IO / memoria
 *   4  limite del generador (0xFFFFFFFF)
 *   5  error de sintaxis del programa de entrada (0xFFFFFFFE)
 *   6  error de tipos, nombre no definido o aridad (0xFFFFFFFD)
 *
 * En cualquier error no se escribe nada en stdout ni en el fichero de salida.
 * La libc vive solo en este adaptador; el objeto Zen no importa simbolos
 * externos (el test lo verifica con `nm -u`).
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define CG_LIMIT 0xFFFFFFFFu
#define CG_SYNTAX 0xFFFFFFFEu
#define CG_TYPES 0xFFFFFFFDu
#define CG_MAX_CAP (64u * 1024u * 1024u)

extern uint64_t zen_codegen_fns(uint64_t source, uint64_t length, uint64_t out,
                                uint64_t cap);

static int read_whole_file(const char *path, unsigned char **buffer,
                           uint64_t *length) {
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        fprintf(stderr, "codegen_functions_driver: cannot open %s\n", path);
        return 0;
    }
    if (fseek(file, 0, SEEK_END) != 0) {
        fprintf(stderr, "codegen_functions_driver: cannot seek %s\n", path);
        fclose(file);
        return 0;
    }
    long size = ftell(file);
    if (size < 0) {
        fprintf(stderr, "codegen_functions_driver: cannot size %s\n", path);
        fclose(file);
        return 0;
    }
    rewind(file);

    size_t capacity = (size_t)size + 1u;
    unsigned char *data = (unsigned char *)malloc(capacity);
    if (data == NULL) {
        fprintf(stderr, "codegen_functions_driver: out of memory\n");
        fclose(file);
        return 0;
    }
    size_t got = fread(data, 1, (size_t)size, file);
    fclose(file);
    if (got != (size_t)size) {
        fprintf(stderr, "codegen_functions_driver: short read on %s\n", path);
        free(data);
        return 0;
    }
    data[size] = 0;
    *buffer = data;
    *length = (uint64_t)got;
    return 1;
}

static int write_output(const char *path, const unsigned char *data,
                        uint64_t length) {
    if (path == NULL) {
        size_t wrote = fwrite(data, 1, (size_t)length, stdout);
        if (wrote != (size_t)length || fflush(stdout) != 0) {
            fprintf(stderr, "codegen_functions_driver: cannot write stdout\n");
            return 0;
        }
        return 1;
    }
    FILE *file = fopen(path, "wb");
    if (file == NULL) {
        fprintf(stderr, "codegen_functions_driver: cannot open %s for writing\n",
                path);
        return 0;
    }
    size_t wrote = fwrite(data, 1, (size_t)length, file);
    int closed = fclose(file);
    if (wrote != (size_t)length || closed != 0) {
        fprintf(stderr, "codegen_functions_driver: cannot write %s\n", path);
        return 0;
    }
    return 1;
}

int main(int argc, char **argv) {
    if (argc != 2 && argc != 3) {
        fprintf(stderr, "usage: %s PROGRAM_FILE [OUTPUT_C]\n", argv[0]);
        return 2;
    }
    unsigned char *source = NULL;
    uint64_t length = 0;
    if (!read_whole_file(argv[1], &source, &length)) {
        return 2;
    }

    /* El limite de tokens del generador hace que la salida sea acotada; este
     * presupuesto es holgado. Si el generador devuelve 0xFFFFFFFF se reintenta
     * con el doble de capacidad antes de informar del limite. */
    uint64_t cap = 65536u;
    if (length <= ((uint64_t)CG_MAX_CAP / 256u)) {
        cap = length * 256u + 65536u;
    } else {
        cap = CG_MAX_CAP;
    }
    if (cap > CG_MAX_CAP) {
        cap = CG_MAX_CAP;
    }

    unsigned char *c_source = NULL;
    uint64_t written = 0;
    for (;;) {
        c_source = (unsigned char *)malloc((size_t)cap + 1u);
        if (c_source == NULL) {
            fprintf(stderr, "codegen_functions_driver: out of memory\n");
            free(source);
            return 2;
        }
        written = zen_codegen_fns((uint64_t)(uintptr_t)source, length,
                                  (uint64_t)(uintptr_t)c_source, cap);
        if (written == CG_LIMIT && cap < CG_MAX_CAP) {
            free(c_source);
            c_source = NULL;
            cap *= 2u;
            if (cap > CG_MAX_CAP) {
                cap = CG_MAX_CAP;
            }
            continue;
        }
        break;
    }

    int rc = 0;
    if (written == CG_LIMIT) {
        fprintf(stderr, "codegen_functions_driver: output or language limit exceeded\n");
        rc = 4;
    } else if (written == CG_SYNTAX) {
        fprintf(stderr, "codegen_functions_driver: syntax error\n");
        rc = 5;
    } else if (written == CG_TYPES) {
        fprintf(stderr, "codegen_functions_driver: type error, undefined name or arity\n");
        rc = 6;
    } else if (written > cap) {
        fprintf(stderr, "codegen_functions_driver: invalid byte count from zen_codegen_fns\n");
        rc = 2;
    } else if (!write_output(argc == 3 ? argv[2] : NULL, c_source, written)) {
        rc = 2;
    }

    free(c_source);
    free(source);
    return rc;
}
