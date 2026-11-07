// SPDX-License-Identifier: GPL-3.0-only
// Exact iOS 16.6/20G75 MediaExperience routing adapter. This changes a transient
// byte in mediaserverd only; no preferences or firmware files are modified.
#include "AudioRoute.h"
#include <cstdint>
#include <cstddef>
#include <climits>
#include <pthread.h>

namespace {
struct AudioLease {
    uint64_t request=0, stamp=0, now=0;
    bool alive=false, coherent=false;
};
static bool ReadAudioNotificationValues(uint64_t &request,uint64_t &stamp,uint64_t &again);
static bool AudioPIDAlive(uint64_t pid);
static uint64_t AudioNowMS();
static void PublishAudioState(uint8_t bits);
static pthread_mutex_t AudioMutex=PTHREAD_MUTEX_INITIALIZER;
static volatile uint8_t *AudioFlag=nullptr;
static void (*NativeAudioSetter)(bool)=nullptr;
static bool AudioOwnHost=false, AudioForcing=false, AudioNativeWanted=false;
static AudioLease AudioCachedLease;

static AudioLease ReadAudioLease() {
    AudioLease s;
    uint64_t again=0;
    if (ReadAudioNotificationValues(s.request,s.stamp,again)) {
        s.coherent=s.request==again;
        uint64_t pid=s.request>>8;
        if (pid>1 && pid<=INT_MAX) s.alive=AudioPIDAlive(pid);
    }
    // A heartbeat can be renewed during either notification or liveness reads.
    // Sampling first would classify that valid renewal as a future timestamp.
    s.now=AudioNowMS();
    return s;
}
static void CacheAudioLeaseLocked(const AudioLease &s) {
    // Notification reads run outside our mutex and can finish out of order.
    if (s.now>=AudioCachedLease.now) AudioCachedLease=s;
}
static AudioLease CurrentAudioLeaseLocked() {
    AudioLease s=AudioCachedLease;
    // Take the clock after copying the protected snapshot: a thread may have
    // waited for a monitor that cached a newer heartbeat while holding the lock.
    s.now=AudioNowMS();
    return s;
}

static bool AudioLeaseValid(const AudioLease &s) {
    uint64_t pid=s.request>>8;
    return s.coherent && (s.request&255)==1 && pid>1 && pid<=INT_MAX &&
        s.alive && s.stamp && s.stamp<=s.now && s.now-s.stamp<=8000;
}
// Caller holds AudioMutex. Native direct stores cannot take our mutex: the
// bounded monitor records observed changes and reasserts only during the lease.
// An intervening native route change remains a device-test limitation.
static void RefreshAudioLocked(const AudioLease &s) {
    if (!AudioFlag || !NativeAudioSetter) return;
    if (AudioForcing && *AudioFlag!=1) AudioNativeWanted=(*AudioFlag!=0);
    bool force=AudioOwnHost && AudioLeaseValid(s);
    if (force && !AudioForcing) {
        AudioNativeWanted=(*AudioFlag!=0);
        AudioForcing=true;
    }
    if (force) {
        if (*AudioFlag!=1) NativeAudioSetter(true);
    } else if (AudioForcing) {
        NativeAudioSetter(AudioNativeWanted);
        AudioForcing=false;
        AudioOwnHost=false; // a new lease requires a fresh native host observation
    }
}
static void AudioSetter(bool wanted) {
    // Never do notify/IPC or lazy dynamic-symbol work while the routing mutex
    // is held. In particular this hook can run while dyld owns its loader lock.
    pthread_mutex_lock(&AudioMutex);
    AudioLease s=CurrentAudioLeaseLocked();
    RefreshAudioLocked(s);
    if (AudioForcing) AudioNativeWanted=wanted;
    if (NativeAudioSetter) NativeAudioSetter(AudioForcing?true:wanted);
    pthread_mutex_unlock(&AudioMutex);
}
static void AudioTick() {
    AudioLease s=ReadAudioLease();
    pthread_mutex_lock(&AudioMutex);
    CacheAudioLeaseLocked(s);
    AudioLease current=CurrentAudioLeaseLocked();
    RefreshAudioLocked(current);
    uint8_t bits=(AudioFlag && *AudioFlag?1:0) | (AudioOwnHost?2:0) |
        (AudioForcing?4:0) | (AudioLeaseValid(current)?8:0);
    pthread_mutex_unlock(&AudioMutex);
    // Only the monitor publishes. The native setter never enters notify, and
    // this lookup/write cannot invert our mutex against dyld's loader lock.
    PublishAudioState(bits);
}
}

extern "C" void CDV3AudioHost(bool own) {
    // Foreign-host release does not need a notification lookup.
    AudioLease s=own?ReadAudioLease():AudioLease{};
    pthread_mutex_lock(&AudioMutex);
    AudioOwnHost=own;
    if (own) CacheAudioLeaseLocked(s);
    RefreshAudioLocked(CurrentAudioLeaseLocked());
    pthread_mutex_unlock(&AudioMutex);
}

#ifndef CDV3_AUDIO_ROUTE_TEST
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach/mach.h>
#include <mach/vm_map.h>
#include "AudioVM.h"
#include <mach/mach_time.h>
#include <notify.h>
#include <signal.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>

namespace {
static int AudioRequestToken=-1, AudioLeaseToken=-1, AudioReadyToken=-1, AudioStateToken=-1;
static dispatch_source_t AudioTimer;
static void (*AudioHookFunction)(void *,void *,void **)=nullptr;
static bool AudioAttempted=false;
static mach_timebase_info_data_t AudioTimebase;
static uint64_t AudioLastPublishedState=UINT64_MAX;

static uint64_t AudioNowMS() {
    // Backend publishes raw Mach ticks with this timebase. Python 3.9's
    // time.monotonic() has a per-process origin and must not be used here.
    if (!AudioTimebase.denom) return 0;
    return (uint64_t)(((__uint128_t)mach_absolute_time()*AudioTimebase.numer)/
                      AudioTimebase.denom/1000000);
}
static bool ReadAudioNotificationValues(uint64_t &request,uint64_t &stamp,uint64_t &again) {
    return AudioRequestToken>=0 && AudioLeaseToken>=0 &&
        notify_get_state(AudioRequestToken,&request)==NOTIFY_STATUS_OK &&
        notify_get_state(AudioLeaseToken,&stamp)==NOTIFY_STATUS_OK &&
        notify_get_state(AudioRequestToken,&again)==NOTIFY_STATUS_OK;
}
static bool AudioPIDAlive(uint64_t pid) {
    return kill((pid_t)pid,0)==0 || errno==EPERM;
}
static void AudioReport(bool ready,NSString *reason,uint8_t code=2) {
    if (AudioReadyToken>=0)
        notify_set_state(AudioReadyToken,((uint64_t)getpid()<<8)|(ready?1:code));
    NSLog(@"CarDashV3Audio ready=%d %@",ready,reason);
}
static void PublishAudioState(uint8_t bits) {
    if (AudioStateToken<0) return;
    uint64_t value=((uint64_t)getpid()<<16)|bits;
    if (value!=AudioLastPublishedState && notify_set_state(AudioStateToken,value)==NOTIFY_STATUS_OK)
        AudioLastPublishedState=value;
}
static bool AudioMapped(uintptr_t address,size_t bytes,vm_prot_t required) {
    return CDV3AudioMapped(address,bytes,required);
}
static void AudioImage(const mach_header *header,intptr_t slide) {
    if (AudioAttempted || header->magic!=MH_MAGIC_64) return;
    constexpr uint8_t wanted[]={0x17,0x90,0xdb,0xae,0x04,0xb6,0x32,0xb7,
        0xb5,0xe7,0xaa,0x39,0xe5,0x71,0xb2,0x08};
    constexpr uint64_t setterAddress=0x195a6450cULL,flagAddress=0x1dd3753e0ULL;
    const uint8_t *p=(const uint8_t *)header+sizeof(mach_header_64);
    const uint8_t *end=p+header->sizeofcmds;
    bool match=false,text=false,data=false;
    for (uint32_t i=0;i<header->ncmds;i++) {
        if (end-p<(ptrdiff_t)sizeof(load_command)) return;
        auto lc=(const load_command *)p;
        if (lc->cmdsize<sizeof(load_command) || lc->cmdsize>(size_t)(end-p)) return;
        if (lc->cmd==LC_UUID && lc->cmdsize==sizeof(uuid_command))
            match=!memcmp(((const uuid_command *)lc)->uuid,wanted,16);
        if (lc->cmd==LC_SEGMENT_64 && lc->cmdsize>=sizeof(segment_command_64)) {
            auto segment=(const segment_command_64 *)lc;
            if (!strncmp(segment->segname,"__TEXT",16) && segment->vmaddr==0x1959c6000ULL &&
                setterAddress>=segment->vmaddr && setterAddress+16<=segment->vmaddr+segment->vmsize &&
                (segment->initprot&(VM_PROT_READ|VM_PROT_EXECUTE))==(VM_PROT_READ|VM_PROT_EXECUTE)) text=true;
            if (!strncmp(segment->segname,"__DATA",16) && flagAddress>=segment->vmaddr &&
                flagAddress<segment->vmaddr+segment->vmsize &&
                (segment->initprot&(VM_PROT_READ|VM_PROT_WRITE))==(VM_PROT_READ|VM_PROT_WRITE)) data=true;
        }
        p+=lc->cmdsize;
    }
    if (!match) return;
    AudioAttempted=true;
    auto setter=(uint8_t *)(setterAddress+slide);
    auto flag=(uint8_t *)(flagAddress+slide);
    constexpr uint8_t prologue[]={0x88,0xc8,0x23,0xb0,0x08,0x21,0x07,0x91,
        0x00,0x61,0x08,0x39,0xc0,0x03,0x5f,0xd6};
    if (!text || !data || !AudioHookFunction ||
        !AudioMapped((uintptr_t)setter,16,VM_PROT_READ|VM_PROT_EXECUTE) ||
        !AudioMapped((uintptr_t)flag,1,VM_PROT_READ|VM_PROT_WRITE) ||
        memcmp(setter,prologue,16) || *flag>1) {
        AudioReport(false,@"MediaExperience identity, mapping, hook provider or prologue mismatch",!text?4:!data?5:!AudioHookFunction?6:!AudioMapped((uintptr_t)setter,16,VM_PROT_READ|VM_PROT_EXECUTE)?7:!AudioMapped((uintptr_t)flag,1,VM_PROT_READ|VM_PROT_WRITE)?8:memcmp(setter,prologue,16)?9:10);return;
    }
    // The hook provider publishes a callable original trampoline. Our mutex
    // blocks an arriving hook until the flag pointer is also published.
    pthread_mutex_lock(&AudioMutex);
    AudioHookFunction(setter,(void *)AudioSetter,(void **)&NativeAudioSetter);
    if (NativeAudioSetter) AudioFlag=flag;
    pthread_mutex_unlock(&AudioMutex);
    if (!NativeAudioSetter) {AudioReport(false,@"Audio setter hook failed",11);return;}
    AudioReport(true,@"Exact MediaExperience adapter loaded; awaiting owned host and live audio lease");
}
__attribute__((constructor)) static void AudioLoad() { @autoreleasepool {
    if (![NSProcessInfo.processInfo.processName isEqual:@"mediaserverd"]) return;
    if (mach_timebase_info(&AudioTimebase)!=KERN_SUCCESS || !AudioTimebase.denom) return;
    (void)AudioNowMS(); // resolve the raw clock path before installing the setter hook
    // Keep registrations alive: canceling the final registration can discard
    // Darwin notification state. No daemon/browser audio preference is written.
    bool registered=notify_register_check("com.cfluid.cardash.v3.audio.request",&AudioRequestToken)==NOTIFY_STATUS_OK;
    registered=(notify_register_check("com.cfluid.cardash.v3.audio.lease",&AudioLeaseToken)==NOTIFY_STATUS_OK)&&registered;
    registered=(notify_register_check("com.cfluid.cardash.v3.audio.ready",&AudioReadyToken)==NOTIFY_STATUS_OK)&&registered;
    registered=(notify_register_check("com.cfluid.cardash.v3.audio.state",&AudioStateToken)==NOTIFY_STATUS_OK)&&registered;
    if (!registered) {AudioReport(false,@"Audio lease notification registration failed");return;}
    AudioReport(false,@"Audio adapter loading");
    void *h=dlopen("/var/jb/usr/lib/libsubstrate.dylib",RTLD_NOW|RTLD_LOCAL);
    AudioHookFunction=h?(void (*)(void *,void *,void **))dlsym(h,"MSHookFunction"):nullptr;
    // Complete dyld's synchronous callbacks before starting a worker that can
    // enter notify. The image callback never reads the notification lease.
    _dyld_register_func_for_add_image(AudioImage);
    if (!AudioAttempted) AudioReport(false,@"Unsupported MediaExperience firmware UUID; no audio hook installed",3);
    AudioTimer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,
        dispatch_queue_create("com.cfluid.cardash.v3.audio-lease",DISPATCH_QUEUE_SERIAL));
    if (!AudioTimer) {AudioReport(false,@"Audio lease monitor unavailable");return;}
    dispatch_source_set_timer(AudioTimer,dispatch_time(DISPATCH_TIME_NOW,0),250*NSEC_PER_MSEC,25*NSEC_PER_MSEC);
    dispatch_source_set_event_handler(AudioTimer,^{AudioTick();});
    dispatch_resume(AudioTimer);
} }
}
#endif
