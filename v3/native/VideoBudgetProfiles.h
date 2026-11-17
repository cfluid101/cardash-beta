// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstdint>
#include <cstring>

enum class CDV3VideoBudgetABI { NetworkInfo, CopyProperty };
struct CDV3VideoBudgetProfile {
    uint8_t uuid[16];
    uintptr_t offset;
    uint8_t prologue[16];
    uint32_t cpuType,cpuSubtype;
    CDV3VideoBudgetABI abi;
};
static const CDV3VideoBudgetProfile *CDV3VideoBudgetFindProfile(const uint8_t *uuid,uint32_t cpuType,uint32_t cpuSubtype) {
    static const CDV3VideoBudgetProfile profiles[]={
        {{0x9c,0xd9,0x4b,0x73,0xb4,0x7b,0x3b,0x7f,0xa8,0x7e,0xde,0x17,0x6f,0xce,0x84,0x1d},
         0x1215dc,{0xff,0x83,0x02,0xd1,0xe9,0x23,0x06,0x6d,0xf6,0x57,0x07,0xa9,0xf4,0x4f,0x08,0xa9},
         0x0100000c,0,CDV3VideoBudgetABI::NetworkInfo},
        // iOS 16.0 20A357 arm64e: network-info logic is inlined in
        // screenstream_CopyProperty, NOT the one-argument 16.6 helper.
        // Binary and ABI evidence: research/carplay-tester-20a357-2026-11-10/video-analysis.
        {{0xd4,0xf5,0x2a,0xaa,0x04,0xc2,0x36,0xa9,0xb0,0xef,0x36,0x60,0xc4,0xa7,0x72,0xf6},
         0x13f8c4,{0x7f,0x23,0x03,0xd5,0xff,0x83,0x04,0xd1,0xe9,0x23,0x0c,0x6d,0xfc,0x6f,0x0d,0xa9},
         0x0100000c,0x80000002,CDV3VideoBudgetABI::CopyProperty},
    };
    if (!uuid) return nullptr;
    for (const auto &profile:profiles)
        if (cpuType==profile.cpuType && cpuSubtype==profile.cpuSubtype && !memcmp(uuid,profile.uuid,16)) return &profile;
    return nullptr;
}
