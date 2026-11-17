// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace CDV3Loopback {
struct Profile {
    const char *name;
    uint8_t uuid[16];
    uint32_t cpuType, cpuSubtype;
    size_t updateOffset, eventOffset, prologueSize;
    uint8_t updateBytes[20], eventBytes[20];
    bool guardedLayout;
};

// The existing 20G75 identity, offsets and 16-byte fingerprints are unchanged.
// Its original UUID-only CPU selection is retained; 20A357 is arm64e-only.
static constexpr Profile Profiles[]={
    {"20G75",{0xbc,0xc4,0x74,0xf5,0x27,0x45,0x36,0x52,0x99,0x5f,0xa0,0x6f,0x65,0x0f,0x76,0xfc},
     0,0,0x55430,0x57ec4,16,
     {0xe9,0x23,0xb9,0x6d,0xfc,0x6f,0x01,0xa9,0xfa,0x67,0x02,0xa9,0xf8,0x5f,0x03,0xa9},
     {0xff,0x83,0x02,0xd1,0xe9,0x23,0x04,0x6d,0xfa,0x67,0x05,0xa9,0xf8,0x5f,0x06,0xa9},false},
    // APTransport SHA256 ca61da7b084aa7e4150ed31f59ee0558314960b0a63dbf3d0858dc50fb63e463.
    // Both entries include PACIBSP. Native arm64e trampoline behavior remains
    // a device validation requirement; never enter four bytes past the symbol.
    {"20A357-arm64e",{0x5e,0x0e,0x47,0x3a,0x63,0xec,0x32,0x93,0xa0,0x97,0xee,0xad,0x34,0x5a,0x82,0x44},
     0x0100000c,0x80000002,0x5aeec,0x5dec0,20,
     {0x7f,0x23,0x03,0xd5,0xe9,0x23,0xb9,0x6d,0xfc,0x6f,0x01,0xa9,0xfa,0x67,0x02,0xa9,0xf8,0x5f,0x03,0xa9},
     {0x7f,0x23,0x03,0xd5,0xff,0x83,0x02,0xd1,0xe9,0x23,0x04,0x6d,0xfa,0x67,0x05,0xa9,0xf8,0x5f,0x06,0xa9},true}
};

static inline const Profile *SelectProfile(const uint8_t *uuid,uint32_t cpuType,uint32_t cpuSubtype) {
    if(!uuid)return nullptr;
    for(const auto &profile:Profiles) {
        if(!memcmp(profile.uuid,uuid,16) &&
           (!profile.cpuType || (profile.cpuType==cpuType && profile.cpuSubtype==cpuSubtype)))return &profile;
    }
    return nullptr;
}

// Caller establishes readable/executable mappings before this byte comparison.
static inline bool MatchEntries(const Profile &profile,const void *update,size_t updateSize,
                                const void *event,size_t eventSize) {
    return update && event && profile.prologueSize && profile.prologueSize<=sizeof(profile.updateBytes) &&
        updateSize>=profile.prologueSize && eventSize>=profile.prologueSize &&
        !memcmp(update,profile.updateBytes,profile.prologueSize) &&
        !memcmp(event,profile.eventBytes,profile.prologueSize);
}

using EntryMapping=bool (*)(uintptr_t,size_t);
static inline bool MappedEntriesMatch(const Profile &profile,uintptr_t base,uint64_t textSize,
                                     EntryMapping mapped,bool *mappingRejected=nullptr) {
    if(mappingRejected)*mappingRejected=true;
    if(!base || !mapped || profile.updateOffset>textSize || profile.eventOffset>textSize ||
       profile.prologueSize>textSize-profile.updateOffset || profile.prologueSize>textSize-profile.eventOffset ||
       profile.updateOffset>UINTPTR_MAX-base || profile.eventOffset>UINTPTR_MAX-base)return false;
    uintptr_t update=base+profile.updateOffset,event=base+profile.eventOffset;
    if(!mapped(update,profile.prologueSize) || !mapped(event,profile.prologueSize))return false;
    if(mappingRejected)*mappingRejected=false;
    return MatchEntries(profile,(const void *)update,profile.prologueSize,(const void *)event,profile.prologueSize);
}
}
