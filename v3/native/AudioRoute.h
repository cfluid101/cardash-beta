// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
// Call with the result of the exact APTransport host-identity check before
// invoking the native update. A foreign/removed host immediately releases audio.
void CDV3AudioHost(bool own);
#ifdef __cplusplus
}
#endif
