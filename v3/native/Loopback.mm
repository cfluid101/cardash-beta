// SPDX-License-Identifier: GPL-3.0-only
// Exact APTransport profiles. No firmware bytes are modified on disk.
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <mutex>
#include <unistd.h>
#include "AudioRoute.h"
#include "AudioVM.h"
#include "LoopbackProfile.h"

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
static bool GuardedLayout=false;
// Optional diagnostic sideband; the existing loopback.ready PID/code ABI stays
// unchanged. Values are decoded by backend/transport.py and never enable hooks.
enum class TransportReason:uint16_t { Ready=0,Loading=1,UnsupportedIdentity=2,
    AdapterArchitecture=3,HookProvider=4,StorageAPI=5,EntryMapping=6,
    EntryPrologue=7,UpdateHook=8,EventHook=9,LiveLayout=10 };

#ifndef CDV3_LOOPBACK_TEST
static void Report(BOOL ready,NSString *error,TransportReason reason);
#endif
static void RejectLayout(void) {
#ifndef CDV3_LOOPBACK_TEST
    Report(NO,@"Exact transport image loaded but live state mapping/type checks failed; no loopback writes made",TransportReason::LiveLayout);
#endif
}
static bool StateMapped(const uint8_t *state) {
    return state && CDV3AudioMapped((uintptr_t)state,0xd0,VM_PROT_READ|VM_PROT_WRITE);
}
static bool OwnedLayoutUsable(const uint8_t *state) {
    if(!StateMapped(state) || state[0x40]>1 || state[0x68]>1 ||
       *(const uint32_t *)(state+0xb8)>2 ||
       !std::isfinite(*(const double *)(state+0x38)) || *(const double *)(state+0x38)<=0 ||
       !std::isfinite(*(const double *)(state+0x48)) || !std::isfinite(*(const double *)(state+0xb0)))return false;
    auto map=*(CFDictionaryRef const *)(state+0x98);
    return map && CDV3AudioMapped((uintptr_t)map,2*sizeof(uintptr_t),VM_PROT_READ) &&
        CFGetTypeID(map)==CFDictionaryGetTypeID();
}


static bool OwnHost(uint8_t *state) {
    if (!state || state[0xa0]!=1) return false;
    id<CDV3LoopbackHost> host=(__bridge id<CDV3LoopbackHost>)*(void **)(state+0xa8);
    Class cls=objc_getClass("CARSessionRequestHost");
    if(GuardedLayout && host && !CDV3AudioMapped((uintptr_t)(__bridge void *)host,2*sizeof(uintptr_t),VM_PROT_READ))return false;
    if (!host || !cls || ![host isKindOfClass:cls]) return false;
    return [[host deviceIdentifier] isEqual:@"02:43:44:4c:41:42"] &&
           [[host displayName] isEqual:@"CarDash V3"] && [host port]==62000 &&
           [host isWiredCarPlaySimulator] &&
           [[host wiredIPv6Addresses] isEqual:@[@"::1"]];
}

static int32_t Update(CFTypeRef helper) {
    uint8_t *s=(uint8_t *)DerivedStorage(helper);
    if(GuardedLayout && !StateMapped(s)) {CDV3AudioHost(helper,false);RejectLayout();return OriginalUpdate(helper);}
    bool own=OwnHost(s);
    CDV3AudioHost(helper,own);
    if (!own) return OriginalUpdate(helper);
    if(GuardedLayout && !OwnedLayoutUsable(s)) {CDV3AudioHost(helper,false);RejectLayout();return OriginalUpdate(helper);}
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
    if(GuardedLayout && !CDV3AudioMapped((uintptr_t)b,0x44,VM_PROT_READ)) {RejectLayout();OriginalEvent(block);return;}
    CFTypeRef helper=*(CFTypeRef *)(b+0x28);
    uint8_t *s=(uint8_t *)DerivedStorage(helper);
    if(GuardedLayout && !StateMapped(s)) {CDV3AudioHost(helper,false);RejectLayout();OriginalEvent(block);return;}
    bool preserve=*(int32_t *)(b+0x40)==4 && OwnHost(s) && *(uint32_t *)(s+0xb8)==1;
    if(GuardedLayout && preserve && !OwnedLayoutUsable(s)) {CDV3AudioHost(helper,false);RejectLayout();OriginalEvent(block);return;}
    CFRetain(helper); // OriginalEvent can consume its final native reference.
    if (preserve) {
        // The native block releases its captured helper before returning.
        // Keep derived storage alive through our post-callback restoration,
        // including when that captured reference was the final native owner.
        // The USB callback still records the real interface change. Suppress
        // only its "USB transport owns this host" release for our loopback host.
        *(uint32_t *)(s+0xb8)=0;
        NSLog(@"CarDashV3Loopback preserving local host during USB change");
    }
    @try { OriginalEvent(block); }
    @finally {
        @try {
            if (preserve && OwnHost(s) && *(uint32_t *)(s+0xb8)==0) *(uint32_t *)(s+0xb8)=1;
            if (!OwnHost(s)) CDV3AudioHost(helper,false);
        }
        @finally { CFRelease(helper); }
    }
}

#ifndef CDV3_LOOPBACK_TEST
#include <notify.h>
static void (*HookFunction)(void *,void *,void **);
static bool attempted=false;
static void Report(BOOL ready, NSString *error,TransportReason reason) {
    // mediaserverd is sandboxed: Darwin notification state avoids file access.
    // Publish only on the existing constructor/hook/error reports, never on a
    // successful update/event path. Sideband failure cannot alter readiness.
    static dispatch_once_t tokensOnce;
    static int reasonToken=-1,readyToken=-1;
    dispatch_once(&tokensOnce,^{
        int token=0;
        if(notify_register_check("com.cfluid.cardash.v3.loopback.ready_reason",&token)==NOTIFY_STATUS_OK)reasonToken=token;
        token=0;
        if(notify_register_check("com.cfluid.cardash.v3.loopback.ready",&token)==NOTIFY_STATUS_OK)readyToken=token;
    });
    static std::mutex reportMutex;
    static uint64_t lastReport=0;
    std::lock_guard<std::mutex> lock(reportMutex);
    const uint16_t code=ready?1:2;
    const uint64_t detail=((uint64_t)getpid()<<32)|((uint64_t)code<<16)|(uint16_t)reason;
    if(detail==lastReport)return;
    lastReport=detail;
    if(reasonToken>=0)notify_set_state(reasonToken,detail);
    if (readyToken>=0) {
        uint64_t state=((uint64_t)getpid()<<8) | (ready?1:2);
        notify_set_state(readyToken,state);
        // Keep the registration alive for the lifetime of this process. A
        // cancelled last registration could discard the readiness state.
    }
    NSLog(@"CarDashV3Loopback ready=%d %@",ready,error);
}
static void Image(const mach_header *header,intptr_t slide) {
    (void)slide;
    if (attempted || !header || !CDV3AudioMapped((uintptr_t)header,sizeof(mach_header_64),VM_PROT_READ))return;
    mach_header_64 parsed={};memcpy(&parsed,header,sizeof(parsed));
    if(parsed.magic!=MH_MAGIC_64 || parsed.ncmds>4096 || parsed.sizeofcmds>1024*1024 ||
       !CDV3AudioMapped((uintptr_t)header,sizeof(parsed)+parsed.sizeofcmds,VM_PROT_READ))return;
    const uint8_t *p=(const uint8_t *)header+sizeof(parsed),*end=p+parsed.sizeofcmds;
    uint8_t uuid[16]={};bool foundUUID=false,foundText=false;uint64_t textSize=0;
    for(uint32_t i=0;i<parsed.ncmds;i++) {
        if((size_t)(end-p)<sizeof(load_command))return;
        load_command command={};memcpy(&command,p,sizeof(command));
        if(command.cmdsize<sizeof(command) || (command.cmdsize&7) || command.cmdsize>(size_t)(end-p))return;
        if(command.cmd==LC_UUID) {
            if(foundUUID || command.cmdsize!=sizeof(uuid_command))return;
            uuid_command identity={};memcpy(&identity,p,sizeof(identity));memcpy(uuid,identity.uuid,16);foundUUID=true;
        } else if(command.cmd==LC_SEGMENT_64) {
            if(command.cmdsize<sizeof(segment_command_64))return;
            segment_command_64 segment={};memcpy(&segment,p,sizeof(segment));
            if(!strncmp(segment.segname,"__TEXT",sizeof(segment.segname))) {
                // Runtime shared-cache segment file offsets need not match an
                // extracted standalone image; bound hooks by VM size/mapping.
                if(foundText || !(segment.initprot&VM_PROT_READ) || !(segment.initprot&VM_PROT_EXECUTE))return;
                foundText=true;textSize=segment.vmsize;
            }
        }
        p+=command.cmdsize;
    }
    if(p!=end || !foundUUID || !foundText)return;
    const auto profile=CDV3Loopback::SelectProfile(uuid,(uint32_t)parsed.cputype,(uint32_t)parsed.cpusubtype);
    if(!profile)return;
    attempted=true;
    uint8_t *base=(uint8_t *)header;
#if !defined(__arm64e__)
    if(profile->guardedLayout) {Report(NO,@"The exact 20A357 profile requires the arm64e adapter slice",TransportReason::AdapterArchitecture);return;}
#endif
    DerivedStorage=(void *(*)(CFTypeRef))dlsym(RTLD_DEFAULT,"CMBaseObjectGetDerivedStorage");
    auto executable=[](uintptr_t address,size_t size){return CDV3AudioMapped(address,size,VM_PROT_READ|VM_PROT_EXECUTE);};
    if(!HookFunction) {Report(NO,@"Transport hook provider is unavailable",TransportReason::HookProvider);return;}
    if(!DerivedStorage) {Report(NO,@"CMBaseObjectGetDerivedStorage is unavailable",TransportReason::StorageAPI);return;}
    bool mappingRejected=false;
    if (!CDV3Loopback::MappedEntriesMatch(*profile,(uintptr_t)base,textSize,executable,&mappingRejected)) {
        Report(NO,mappingRejected?@"Transport entry bounds or executable mapping mismatch":@"Transport entry instruction fingerprint mismatch",
               mappingRejected?TransportReason::EntryMapping:TransportReason::EntryPrologue);return;
    }
    GuardedLayout=profile->guardedLayout;
    NSLog(@"CarDashV3Loopback matched profile=%s update=0x%zx event=0x%zx guardedLayout=%d",profile->name,profile->updateOffset,profile->eventOffset,GuardedLayout);
    HookFunction(base+profile->updateOffset,(void *)Update,(void **)&OriginalUpdate);
    if (!OriginalUpdate) { Report(NO,@"Transport update hook failed",TransportReason::UpdateHook);return; }
    HookFunction(base+profile->eventOffset,(void *)Event,(void **)&OriginalEvent);
    Report(OriginalEvent!=nullptr,OriginalEvent?@"":@"Transport disconnect hook failed",OriginalEvent?TransportReason::Ready:TransportReason::EventHook);
}

__attribute__((constructor)) static void Load(void) { @autoreleasepool {
    if (![NSProcessInfo.processInfo.processName isEqual:@"mediaserverd"]) return;
    void *h=dlopen("/var/jb/usr/lib/libsubstrate.dylib",RTLD_NOW|RTLD_LOCAL);
    HookFunction=h?(void (*)(void *,void *,void **))dlsym(h,"MSHookFunction"):nullptr;
    NSLog(@"CarDashV3Loopback loading provider=%d",HookFunction!=nullptr);
    Report(NO,@"Transport adapter loading",TransportReason::Loading);
    _dyld_register_func_for_add_image(Image);
    if (!attempted) Report(NO,@"Unsupported APTransport firmware UUID or CPU; no hooks installed",TransportReason::UnsupportedIdentity);
} }
#endif

