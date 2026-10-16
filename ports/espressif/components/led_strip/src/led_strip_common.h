/*
 * SPDX-FileCopyrightText: 2022-2025 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#pragma once

#include <stdbool.h>
#include <stdatomic.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief State of a strip transaction, used to serialize the access to the shared pixel buffer
 *
 * @note This state machine only prevents two tasks from starting a transaction at the same time.
 *       It does not provide ordering between tasks, nor does it make the driver as a whole
 *       thread-safe. See the "Thread safety" note in the public API documentation.
 */
typedef enum {
    LED_STRIP_TRANS_IDLE,     /*!< No transaction is running, the pixel buffer can be modified freely */
    LED_STRIP_TRANS_INFLIGHT, /*!< A transaction has been started but is still being transferred by the peripheral
                                   (i.e. it is "in the air"). The pixel buffer must not be modified, otherwise the
                                   peripheral may send a mix of old and new data. Use the wait API to join it */
    LED_STRIP_TRANS_LOCKED,   /*!< The local critical section is taken by the current task, e.g. while it is writing
                                   the pixel buffer or blocking to wait for a transaction to finish. The peripheral
                                   itself may or may not be transmitting at this point. This state is only ever
                                   held for the duration of a single driver call */
} led_strip_trans_state_t;

typedef atomic_int led_strip_trans_state_atomic_t;

static inline bool led_strip_trans_state_try_set(led_strip_trans_state_atomic_t *state, led_strip_trans_state_t expected, led_strip_trans_state_t desired)
{
    int expected_state = expected;
    return atomic_compare_exchange_strong(state, &expected_state, desired);
}

#ifdef __cplusplus
}
#endif
