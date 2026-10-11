/* ARMv7 softfp: map Samsung's default 7200 seconds to the owner's 300.
 * All other values and the native eligibility/wake functions are unchanged.
 * Tail call the firmware-guarded e_screensaver_timeout_set (Thumb address).
 * Loaded only in existing module padding; never an on-disk module override.
 */
.syntax unified
.thumb
.text
.global timeout_policy
.thumb_func
timeout_policy:
    cmp r0, #0
    bne native
    movw r2, #0x2000
    movt r2, #0x40bc
    cmp r1, r2
    bne native
    movw r1, #0xc000
    movt r1, #0x4072
native:
    ldr r3, original
    bx r3
.balign 4
original:
    .word 0x000bbf71
