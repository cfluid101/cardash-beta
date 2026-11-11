// SPDX-License-Identifier: GPL-3.0-only
#import <Foundation/Foundation.h>
#include <cstdint>
#include <atomic>
#include "VideoBudgetProfiles.h"
static std::atomic<uint64_t> BudgetObserved{0};
static CFDictionaryRef (*BudgetOriginal)(uint8_t *)=nullptr;
static int32_t (*BudgetOriginalCopyProperty)(CFTypeRef,CFStringRef,CFAllocatorRef,CFTypeRef *)=nullptr;
static uint8_t *(*BudgetDerivedStorage)(CFTypeRef)=nullptr;
static int32_t (*BudgetDisplayProperty)(CFTypeRef,CFStringRef,CFAllocatorRef,CFTypeRef *)=nullptr;
static CFStringRef BudgetUUIDKey=nullptr,BudgetBandwidthKey=nullptr;
static CFStringRef BudgetNetworkInfoKey=nullptr;
static uint32_t BudgetRequested();
static bool BudgetStateReadable(const uint8_t *state);
static CFDictionaryRef BudgetClampDictionary(CFDictionaryRef original,uint8_t *state,CFAllocatorRef allocator) {
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
    CFMutableDictionaryRef result=CFDictionaryCreateMutableCopy(allocator,0,original);
    if (!result) return original;
    int32_t bps=(int32_t)requested;
    CFNumberRef number=CFNumberCreate(allocator,kCFNumberSInt32Type,&bps);
    if (!number) {CFRelease(result);return original;}
    CFDictionarySetValue(result,BudgetBandwidthKey,number);
    BudgetObserved.store(((uint64_t)previous<<32)|requested);
    CFRelease(number);CFRelease(original);return result;
}
static CFDictionaryRef BudgetNetworkInfo(uint8_t *state) {
    return BudgetClampDictionary(BudgetOriginal(state),state,kCFAllocatorDefault);
}
static int32_t BudgetCopyProperty(CFTypeRef object,CFStringRef key,CFAllocatorRef allocator,CFTypeRef *out) {
    // Preserve native congestion/FPS calculations, status, output ownership and
    // the caller's allocator. Only a successful NetworkInfo Copy may be replaced.
    int32_t status=BudgetOriginalCopyProperty(object,key,allocator,out);
    if (status || !object || !out || !*out || !BudgetRequested() || !key ||
        !BudgetNetworkInfoKey || !BudgetDerivedStorage ||
        CFGetTypeID(key)!=CFStringGetTypeID() || !CFEqual(key,BudgetNetworkInfoKey) ||
        CFGetTypeID(*out)!=CFDictionaryGetTypeID()) return status;
    uint8_t *state=BudgetDerivedStorage(object);
    if (!state || !BudgetStateReadable(state)) return status;
    *out=BudgetClampDictionary((CFDictionaryRef)*out,state,allocator);
    return status;
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
static bool BudgetStateReadable(const uint8_t *state) {
    return CDV3AudioMapped((uintptr_t)state,0x153,VM_PROT_READ);
}
static std::atomic<uint32_t> BudgetBits{0};
static int BudgetReadyToken=-1,BudgetReasonToken=-1,BudgetRequestToken=-1,BudgetLeaseToken=-1,BudgetStateToken=-1,BudgetObservedToken=-1;
static mach_timebase_info_data_t BudgetTimebase;
static dispatch_source_t BudgetTimer;
static bool BudgetAttempted=false;
static void (*BudgetHook)(void *,void *,void **)=nullptr;
static uint32_t BudgetRequested() {return BudgetBits.load();}
static void BudgetReport(bool ready,NSString *reason,uint32_t code=0) {
    // Optional diagnostic sideband: PID:32 | readiness:16 | reason:16.
    // Publish before readiness; readers discard a mismatched/transitional pair.
    if (BudgetReasonToken>=0) notify_set_state(BudgetReasonToken,
        ((uint64_t)getpid()<<32)|((uint64_t)(ready?1:2)<<16)|(code&0xffff));
    if (BudgetReadyToken>=0) notify_set_state(BudgetReadyToken,((uint64_t)getpid()<<8)|(ready?1:2));
    NSLog(@"CarDashV3VideoBudget ready=%d code=%u %@",ready,code,reason);
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
    if (BudgetAttempted || !CDV3AudioMapped((uintptr_t)header,sizeof(mach_header_64),VM_PROT_READ)) return;
    const auto mh=(const mach_header_64 *)header;
    if (mh->magic!=MH_MAGIC_64 || mh->ncmds>4096 || mh->sizeofcmds>1024*1024) return;
    const size_t headerSize=sizeof(*mh)+mh->sizeofcmds;
    if ((uintptr_t)header>UINTPTR_MAX-headerSize || !CDV3AudioMapped((uintptr_t)header,headerSize,VM_PROT_READ)) return;
    const CDV3VideoBudgetProfile *profile=nullptr;
    const uint8_t *p=(const uint8_t *)header+sizeof(mach_header_64);
    const uint8_t *end=(const uint8_t *)header+headerSize;
    for (uint32_t i=0;i<mh->ncmds;i++) {
        if ((size_t)(end-p)<sizeof(load_command)) return;
        const auto lc=(const load_command *)p;
        if (lc->cmdsize<sizeof(load_command) || lc->cmdsize>(size_t)(end-p)) return;
        if(lc->cmd==LC_UUID && lc->cmdsize==sizeof(uuid_command))
            profile=CDV3VideoBudgetFindProfile(((const uuid_command *)lc)->uuid,(uint32_t)mh->cputype,(uint32_t)mh->cpusubtype);
        p+=lc->cmdsize;
    }
    if (!profile) return;BudgetAttempted=true;
#if !defined(__arm64e__)
    if (profile->abi==CDV3VideoBudgetABI::CopyProperty) {BudgetReport(false,@"20A357 requires the arm64e adapter slice",10);return;}
#endif
    if ((uintptr_t)header>UINTPTR_MAX-profile->offset) {BudgetReport(false,@"Video entry address overflow",1);return;}
    auto entry=(uint8_t *)header+profile->offset;
    auto uuidKey=(CFStringRef *)dlsym(RTLD_DEFAULT,"kAPEndpointDisplayDescriptionProperty_UUID");
    auto bandwidthKey=(CFStringRef *)dlsym(RTLD_DEFAULT,"kFigVirtualDisplaySinkNetworkInfoKey_Bandwidth");
    BudgetDisplayProperty=(decltype(BudgetDisplayProperty))dlsym(RTLD_DEFAULT,"APEndpointDisplayDescriptionCopyProperty");
    if (!BudgetHook) {BudgetReport(false,@"Hook provider unavailable",2);return;}
    if (!BudgetDisplayProperty || !uuidKey || !bandwidthKey) {BudgetReport(false,@"Video symbols unavailable",3);return;}
    if (!CDV3AudioMapped((uintptr_t)entry,16,VM_PROT_READ|VM_PROT_EXECUTE)) {BudgetReport(false,@"Video entry mapping mismatch",4);return;}
    if (memcmp(entry,profile->prologue,16)) {BudgetReport(false,@"Video entry prologue mismatch",5);return;}
    BudgetUUIDKey=*uuidKey;BudgetBandwidthKey=*bandwidthKey;
    if (!BudgetUUIDKey || !BudgetBandwidthKey ||
        CFGetTypeID(BudgetUUIDKey)!=CFStringGetTypeID() || CFGetTypeID(BudgetBandwidthKey)!=CFStringGetTypeID()) {
        BudgetReport(false,@"Video property key type mismatch",6);return;
    }
    if (profile->abi==CDV3VideoBudgetABI::CopyProperty) {
        auto networkKey=(CFStringRef *)dlsym(RTLD_DEFAULT,"kFigVirtualDisplaySinkProperty_NetworkInfo");
        BudgetDerivedStorage=(decltype(BudgetDerivedStorage))dlsym(RTLD_DEFAULT,"CMBaseObjectGetDerivedStorage");
        BudgetNetworkInfoKey=networkKey?*networkKey:nullptr;
        if (!BudgetDerivedStorage || !BudgetNetworkInfoKey || CFGetTypeID(BudgetNetworkInfoKey)!=CFStringGetTypeID()) {
            BudgetReport(false,@"CopyProperty symbols or network key mismatch",7);return;
        }
        BudgetHook(entry,(void *)BudgetCopyProperty,(void **)&BudgetOriginalCopyProperty);
        BudgetReport(BudgetOriginalCopyProperty!=nullptr,BudgetOriginalCopyProperty?@"20A357 CopyProperty":@"CopyProperty hook failed",BudgetOriginalCopyProperty?0:8);
        return;
    }
    BudgetHook(entry,(void *)BudgetNetworkInfo,(void **)&BudgetOriginal);
    BudgetReport(BudgetOriginal!=nullptr,BudgetOriginal?@"":@"Network-info hook failed",BudgetOriginal?0:8);
}
__attribute__((constructor)) static void BudgetLoad() { @autoreleasepool {
    if (![NSProcessInfo.processInfo.processName isEqual:@"mediaserverd"]) return;
    void *provider=dlopen("/var/jb/usr/lib/libsubstrate.dylib",RTLD_NOW|RTLD_LOCAL);
    BudgetHook=provider?(decltype(BudgetHook))dlsym(provider,"MSHookFunction"):nullptr;
    notify_register_check("com.cfluid.cardash.v3.video.ready",&BudgetReadyToken);
    int reasonToken=-1;
    if (notify_register_check("com.cfluid.cardash.v3.video.ready_reason",&reasonToken)==NOTIFY_STATUS_OK)
        BudgetReasonToken=reasonToken;
    notify_register_check("com.cfluid.cardash.v3.video.request",&BudgetRequestToken);
    notify_register_check("com.cfluid.cardash.v3.video.lease",&BudgetLeaseToken);
    notify_register_check("com.cfluid.cardash.v3.video.state",&BudgetStateToken);
    notify_register_check("com.cfluid.cardash.v3.video.observed",&BudgetObservedToken);
    mach_timebase_info(&BudgetTimebase);
    _dyld_register_func_for_add_image(BudgetImage);
    if (!BudgetAttempted) BudgetReport(false,@"Unsupported AirPlaySender identity or header; no hook installed",9);
    BudgetTimer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,dispatch_get_global_queue(QOS_CLASS_UTILITY,0));
    dispatch_source_set_timer(BudgetTimer,dispatch_time(DISPATCH_TIME_NOW,0),250*NSEC_PER_MSEC,25*NSEC_PER_MSEC);
    dispatch_source_set_event_handler(BudgetTimer,^{ BudgetTick(); });dispatch_resume(BudgetTimer);
} }
#endif
