// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
// Call with the result of the exact APTransport host-identity check before
// invoking the native update. Removal can revoke only that helper's ownership.
void CDV3AudioHost(const void *helper,bool own);
#ifdef __cplusplus
}
#endif
