/* Linux x86_64 test adapter only: entry and byte output without libc.
 * No privileged instructions and no claim of kernel boot.
 */
.section .text
.global _start
.type _start, @function
_start:
    xor %ebp, %ebp
    call kernel_entry
    mov %eax, %edi
    mov $60, %eax
    syscall
    ud2
.size _start, .-_start

.global emit_byte
.type emit_byte, @function
emit_byte:
    sub $8, %rsp
    mov %dil, (%rsp)
    mov $1, %eax
    mov $1, %edi
    mov %rsp, %rsi
    mov $1, %edx
    syscall
    cmp $1, %rax
    jne .Lwrite_failed
    add $8, %rsp
    ret
.Lwrite_failed:
    mov $1, %edi
    mov $60, %eax
    syscall
    ud2
.size emit_byte, .-emit_byte
.section .note.GNU-stack,"",@progbits
