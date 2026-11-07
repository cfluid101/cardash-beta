// SPDX-License-Identifier: GPL-3.0-only
#import <Foundation/Foundation.h>
#include <cstdint>
#include <atomic>
static std::atomic<uint64_t> BudgetObserved{0};
static CFDictionaryRef (*BudgetOriginal)(uint8_t *)=nullptr;
static int32_t (*BudgetDisplayProperty)(CFTypeRef,CFStringRef,CFAllocatorRef,CFTypeRef *)=nullptr;
static CFStringRef BudgetUUIDKey=nullptr,BudgetBandwidthKey=nullptr;
static uint32_t BudgetRequested();
static CFDictionaryRef BudgetNetworkInfo(uint8_t *state) {
    CFDictionaryRef original=BudgetOriginal(state);
    uint32_t requested=BudgetRequested();
    if (!original || !requested || !state || !state[0x150] || !state[0x152] ||
        !BudgetDisplayProperty || !BudgetUUIDKey || !BudgetBandwidthKey) return original;
    // Verified StreamScreenStorage.displayDescription on this exact image.
    CFTypeRef display=*(CFTypeRef *)(state+0x38), uuid=nullptr;
    if (!display) return original;
    int32_t error=BudgetDisplayProperty(display,BudgetUUIDKey,kCFAllocatorDefault,&uuid);
    bool own=!error && uuid && CFGetTypeID(uuid)==CFStringGetTypeID() &&
        CFEqual(uuid,CFSTR("b7e6c5a0-1111-4000-8000-000000000001"));
    if (uuid) CFRelease(uuid);
    if (!own || CFGetTypeID(original)!=CFDictionaryGetTypeID()) return original;
    CFTypeRef prior=CFDictionaryGetValue(original,BudgetBandwidthKey);
    int64_t previous=0;
    if (!prior || CFGetTypeID(prior)!=CFNumberGetTypeID() ||
        !CFNumberGetValue((CFNumberRef)prior,kCFNumberSInt64Type,&previous) || previous<=requested) return original;
    CFMutableDictionaryRef result=CFDictionaryCreateMutableCopy(kCFAllocatorDefault,0,original);
    if (!result) return original;
    int32_t bps=(int32_t)requested;
    CFNumberRef number=CFNumberCreate(kCFAllocatorDefault,kCFNumberSInt32Type,&bps);
    if (!number) {CFRelease(result);return original;}
    CFDictionarySetValue(result,BudgetBandwidthKey,number);
    BudgetObserved.store(((uint64_t)previous<<32)|requested);
    CFRelease(number);CFRelease(original);return result;
}

#ifndef CDV3_VIDEO_BUDGET_TEST
#include <atomic>
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach/mach_time.h>
#include <notify.h>
#include <signal.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>
#include "AudioVM.h"
static std::atomic<uint32_t> BudgetBits{0};
static int BudgetReadyToken=-1,BudgetRequestToken=-1,BudgetLeaseToken=-1,BudgetStateToken=-1,BudgetObservedToken=-1;
static mach_timebase_info_data_t BudgetTimebase;
static dispatch_source_t BudgetTimer;
static bool BudgetAttempted=false;
static void (*BudgetHook)(void *,void *,void **)=nullptr;
static uint32_t BudgetRequested() {return BudgetBits.load();}
static void BudgetReport(bool ready,NSString *reason) {
    if (BudgetReadyToken>=0) notify_set_state(BudgetReadyToken,((uint64_t)getpid()<<8)|(ready?1:2));
    NSLog(@"CarDashV3VideoBudget ready=%d %@",ready,reason);
}
static void BudgetTick() {
    uint64_t request=0,stamp=0,again=0;
    bool read=BudgetRequestToken>=0 && BudgetLeaseToken>=0 && BudgetTimebase.denom &&
        notify_get_state(BudgetRequestToken,&request)==0 && notify_get_state(BudgetLeaseToken,&stamp)==0 &&
        notify_get_state(BudgetRequestToken,&again)==0 && request==again;
    uint64_t now=BudgetTimebase.denom?(uint64_t)(((__uint128_t)mach_absolute_time()*BudgetTimebase.numer)/BudgetTimebase.denom/1000000):0;
    uint32_t pid=request>>32,bps=request&0xffffffff;
    bool valid=read && pid>1 && pid<=INT32_MAX && bps>=750000 && bps<=6000000 &&
        stamp && stamp<=now && now-stamp<=8000 && (kill((pid_t)pid,0)==0 || errno==EPERM);
    bps=valid?bps:0;
    if (!bps) BudgetObserved.store(0);
    if (BudgetObservedToken>=0) notify_set_state(BudgetObservedToken,BudgetObserved.load());
    if (BudgetBits.exchange(bps)!=bps) {
        NSLog(@"CarDashV3VideoBudget request=%u bps",bps);
        if (BudgetStateToken>=0) notify_set_state(BudgetStateToken,((uint64_t)getpid()<<32)|bps);
    }
}
static void BudgetImage(const mach_header *header,intptr_t slide) {
    (void)slide;
    if (BudgetAttempted || header->magic!=MH_MAGIC_64) return;
    const uint8_t uuid[]={0x9c,0xd9,0x4b,0x73,0xb4,0x7b,0x3b,0x7f,0xa8,0x7e,0xde,0x17,0x6f,0xce,0x84,0x1d};
    const uint8_t *p=(const uint8_t *)header+sizeof(mach_header_64);bool match=false;
    for (uint32_t i=0;i<header->ncmds;i++) {const auto lc=(const load_command *)p;
        if(lc->cmd==LC_UUID && lc->cmdsize==sizeof(uuid_command))match=!memcmp(((const uuid_command *)lc)->uuid,uuid,16);
        p+=lc->cmdsize;
    }
    if (!match) return;BudgetAttempted=true;
    auto entry=(uint8_t *)header+0x1215dc;
    const uint8_t bytes[]={0xff,0x83,0x02,0xd1,0xe9,0x23,0x06,0x6d,0xf6,0x57,0x07,0xa9,0xf4,0x4f,0x08,0xa9};
    auto uuidKey=(CFStringRef *)dlsym(RTLD_DEFAULT,"kAPEndpointDisplayDescriptionProperty_UUID");
    auto bandwidthKey=(CFStringRef *)dlsym(RTLD_DEFAULT,"kFigVirtualDisplaySinkNetworkInfoKey_Bandwidth");
    BudgetDisplayProperty=(decltype(BudgetDisplayProperty))dlsym(RTLD_DEFAULT,"APEndpointDisplayDescriptionCopyProperty");
    if (!BudgetHook || !BudgetDisplayProperty || !uuidKey || !bandwidthKey ||
        !CDV3AudioMapped((uintptr_t)entry,16,VM_PROT_READ|VM_PROT_EXECUTE) || memcmp(entry,bytes,16)) {
        BudgetReport(false,@"Exact firmware, symbols, or hook provider mismatch");return;
    }
    BudgetUUIDKey=*uuidKey;BudgetBandwidthKey=*bandwidthKey;
    BudgetHook(entry,(void *)BudgetNetworkInfo,(void **)&BudgetOriginal);
    BudgetReport(BudgetOriginal!=nullptr,BudgetOriginal?@"":@"Network-info hook failed");
}
__attribute__((constructor)) static void BudgetLoad() { @autoreleasepool {
    if (![NSProcessInfo.processInfo.processName isEqual:@"mediaserverd"]) return;
    void *provider=dlopen("/var/jb/usr/lib/libsubstrate.dylib",RTLD_NOW|RTLD_LOCAL);
    BudgetHook=provider?(decltype(BudgetHook))dlsym(provider,"MSHookFunction"):nullptr;
    notify_register_check("com.cfluid.cardash.v3.video.ready",&BudgetReadyToken);
    notify_register_check("com.cfluid.cardash.v3.video.request",&BudgetRequestToken);
    notify_register_check("com.cfluid.cardash.v3.video.lease",&BudgetLeaseToken);
    notify_register_check("com.cfluid.cardash.v3.video.state",&BudgetStateToken);
    notify_register_check("com.cfluid.cardash.v3.video.observed",&BudgetObservedToken);
    mach_timebase_info(&BudgetTimebase);
    _dyld_register_func_for_add_image(BudgetImage);
    if (!BudgetAttempted) BudgetReport(false,@"Unsupported AirPlaySender image; no hook installed");
    BudgetTimer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,dispatch_get_global_queue(QOS_CLASS_UTILITY,0));
    dispatch_source_set_timer(BudgetTimer,dispatch_time(DISPATCH_TIME_NOW,0),250*NSEC_PER_MSEC,25*NSEC_PER_MSEC);
    dispatch_source_set_event_handler(BudgetTimer,^{ BudgetTick(); });dispatch_resume(BudgetTimer);
} }
#endif
