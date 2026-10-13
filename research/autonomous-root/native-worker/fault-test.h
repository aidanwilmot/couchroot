/* Fault injection exists only in the separately named acceptance-test binary.
 * Original Couchroot code. SPDX-License-Identifier: 0BSD */
#ifdef NATIVE_WORKER_FAULT_TEST
#include <sys/mman.h>
static int fault_test_requested;
static void *fault_test_memory(void *unused) {
  (void)unused;
  void *page = mmap(NULL, 4096, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (page == MAP_FAILED)
    _exit(124);
  *(volatile unsigned char *)page = 1; /* Real protection fault, not raise(). */
  _exit(124);
}
static void fault_test_execute(void) {
  if (fault_test_requested == 1)
    fault_test_memory(NULL);
  if (fault_test_requested == 2) {
    pthread_t thread;
    if (pthread_create(&thread, NULL, fault_test_memory, NULL))
      _exit(124);
    pthread_join(thread, NULL);
    _exit(124);
  }
}
#endif
