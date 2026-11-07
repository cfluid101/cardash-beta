// SPDX-License-Identifier: GPL-3.0-only
// Exact iOS 16.6 / 20G75 APTransport adapter. No firmware bytes are modified on disk.
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <cstring>
#include <cstdint>
#include <unistd.h>
#ifdef CDV3_LOOPBACK_TEST
static void CDV3AudioHost(bool) {}
#else
#include "AudioRoute.h"
#endif

@protocol CDV3LoopbackHost <NSObject>
- (id)deviceIdentifier;
- (id)displayName;
- (id)wiredIPv6Addresses;
- (long long)port;
- (BOOL)isWiredCarPlaySimulator;
@end

static void *(*DerivedStorage)(CFTypeRef);
static int32_t (*OriginalUpdate)(CFTypeRef);
static void (*OriginalEvent)(void *);


static bool OwnHost(uint8_t *state) {
    if (!state || state[0xa0]!=1) return false;
    id<CDV3LoopbackHost> host=(__bridge id<CDV3LoopbackHost>)*(void **)(state+0xa8);
    Class cls=objc_getClass("CARSessionRequestHost");
    if (!host || !cls || ![host isKindOfClass:cls]) return false;
    return [[host deviceIdentifier] isEqual:@"02:43:44:4c:41:42"] &&
           [[host displayName] isEqual:@"CarDash V3"] && [host port]==62000 &&
           [host isWiredCarPlaySimulator] &&
           [[host wiredIPv6Addresses] isEqual:@[@"::1"]];
}

static int32_t Update(CFTypeRef helper) {
    uint8_t *s=(uint8_t *)DerivedStorage(helper);
    bool own=OwnHost(s);
    CDV3AudioHost(own);
    if (!own) return OriginalUpdate(helper);
    CFDictionaryRef originalMap=*(CFDictionaryRef *)(s+0x98);
    if (!originalMap || CFGetTypeID(originalMap)!=CFDictionaryGetTypeID()) return OriginalUpdate(helper);
    CFMutableDictionaryRef map=CFDictionaryCreateMutableCopy(kCFAllocatorDefault,0,originalMap);
    if (!map) return OriginalUpdate(helper);
    CFDictionarySetValue(map,CFSTR("lo0"),(__bridge CFArrayRef)@[@"::1"]);
    uint8_t usb=s[0x40],wifi=s[0x68];
    CFStringRef interfaceName=*(CFStringRef *)(s+0x50);
    uint32_t transport=*(uint32_t *)(s+0x58);
    double connectedAt=*(double *)(s+0x48);
    // These are inputs to the verified network-state function. Its resulting
    // endpoint owns its references; physical interface inputs are restored.
    s[0x40]=1;s[0x68]=0;
    *(CFStringRef *)(s+0x50)=CFSTR("lo0");
    *(uint32_t *)(s+0x58)=8;
    *(double *)(s+0x48)=*(double *)(s+0xb0);
    *(CFDictionaryRef *)(s+0x98)=map;
    int32_t result;
    @try { result=OriginalUpdate(helper); }
    @finally {
        s[0x40]=usb;s[0x68]=wifi;
        *(CFStringRef *)(s+0x50)=interfaceName;
        *(uint32_t *)(s+0x58)=transport;
        *(double *)(s+0x48)=connectedAt;
        *(CFDictionaryRef *)(s+0x98)=originalMap;
        CFRelease(map);
    }
    NSLog(@"CarDashV3Loopback update result=%d transport=%u interface=%@",result,*(uint32_t *)(s+0xb8),(__bridge id)*(CFStringRef *)(s+0xc8));
    return result;
}

static void Event(void *block) {
    uint8_t *b=(uint8_t *)block;
    CFTypeRef helper=*(CFTypeRef *)(b+0x28);
    uint8_t *s=(uint8_t *)DerivedStorage(helper);
    bool preserve=*(int32_t *)(b+0x40)==4 && OwnHost(s) && *(uint32_t *)(s+0xb8)==1;
    if (preserve) {
        // The native block releases its captured helper before returning.
        // Keep derived storage alive through our post-callback restoration,
        // including when that captured reference was the final native owner.
        CFRetain(helper);
        // The USB callback still records the real interface change. Suppress
        // only its "USB transport owns this host" release for our loopback host.
        *(uint32_t *)(s+0xb8)=0;
        NSLog(@"CarDashV3Loopback preserving local host during USB change");
    }
    @try { OriginalEvent(block); }
    @finally {
        if (preserve) {
            @try {
                if (OwnHost(s) && *(uint32_t *)(s+0xb8)==0) *(uint32_t *)(s+0xb8)=1;
            }
            @finally { CFRelease(helper); }
        }
    }
}

#ifndef CDV3_LOOPBACK_TEST
#include <notify.h>
static void (*HookFunction)(void *,void *,void **);
static bool attempted=false;
static void Report(BOOL ready, NSString *error) {
    // mediaserverd is sandboxed: Darwin notification state avoids file access.
    int token=0;
    if (notify_register_check("com.cfluid.cardash.v3.loopback.ready",&token)==NOTIFY_STATUS_OK) {
        uint64_t state=((uint64_t)getpid()<<8) | (ready?1:2);
        notify_set_state(token,state);
        // Keep the registration alive for the lifetime of this process. A
        // cancelled last registration could discard the readiness state.
    }
    NSLog(@"CarDashV3Loopback ready=%d %@",ready,error);
}
static void Image(const mach_header *header,intptr_t slide) {
    (void)slide;
    if (attempted || header->magic!=MH_MAGIC_64) return;
    const uint8_t wanted[]={0xbc,0xc4,0x74,0xf5,0x27,0x45,0x36,0x52,0x99,0x5f,0xa0,0x6f,0x65,0x0f,0x76,0xfc};
    const uint8_t *p=(const uint8_t *)header+sizeof(mach_header_64);bool match=false;
    for (uint32_t i=0;i<header->ncmds;i++) {
        const load_command *lc=(const load_command *)p;
        if (lc->cmd==LC_UUID && lc->cmdsize==sizeof(uuid_command)) match=!memcmp(((const uuid_command *)lc)->uuid,wanted,16);
        p+=lc->cmdsize;
    }
    if (!match) return;
    attempted=true;
    uint8_t *base=(uint8_t *)header;
    const uint8_t updateBytes[]={0xe9,0x23,0xb9,0x6d,0xfc,0x6f,0x01,0xa9,0xfa,0x67,0x02,0xa9,0xf8,0x5f,0x03,0xa9};
    const uint8_t eventBytes[]={0xff,0x83,0x02,0xd1,0xe9,0x23,0x04,0x6d,0xfa,0x67,0x05,0xa9,0xf8,0x5f,0x06,0xa9};
    DerivedStorage=(void *(*)(CFTypeRef))dlsym(RTLD_DEFAULT,"CMBaseObjectGetDerivedStorage");
    if (!HookFunction || !DerivedStorage || memcmp(base+0x55430,updateBytes,16) || memcmp(base+0x57ec4,eventBytes,16)) {
        Report(NO,@"Transport adapter unavailable: hook provider, storage API or firmware prologue mismatch");return;
    }
    HookFunction(base+0x55430,(void *)Update,(void **)&OriginalUpdate);
    if (!OriginalUpdate) { Report(NO,@"Transport update hook failed");return; }
    HookFunction(base+0x57ec4,(void *)Event,(void **)&OriginalEvent);
    Report(OriginalEvent!=nullptr,OriginalEvent?@"":@"Transport disconnect hook failed");
}

__attribute__((constructor)) static void Load(void) { @autoreleasepool {
    if (![NSProcessInfo.processInfo.processName isEqual:@"mediaserverd"]) return;
    void *h=dlopen("/var/jb/usr/lib/libsubstrate.dylib",RTLD_NOW|RTLD_LOCAL);
    HookFunction=h?(void (*)(void *,void *,void **))dlsym(h,"MSHookFunction"):nullptr;
    NSLog(@"CarDashV3Loopback loading provider=%d",HookFunction!=nullptr);
    Report(NO,@"Transport adapter loading");
    _dyld_register_func_for_add_image(Image);
    if (!attempted) Report(NO,@"Unsupported APTransport firmware UUID; no hooks installed");
} }
#endif

