#define CDV3_AUDIO_ROUTE_TEST 1
#include "../native/AudioRoute.mm"
#include "../native/AudioVM.h"
#include <cassert>
#include <cstdio>
#include <thread>
#include <atomic>
#include <cerrno>

namespace {
static AudioLease MockLease;
static uint8_t MockFlag=0;
static bool CheckReadMutex=true;
static bool RequireLockedClock=false,RenewDuringRead=false;
static uint64_t AdvanceDuringLiveness=0;
static std::atomic<unsigned> LeaseReads{0};
static uint8_t PublishedBits=255;
static unsigned StateChanges=0;
static bool NewHostDuringRead=false,RemoveHostDuringRead=false;
static uint64_t AudioNowMS() {
    if (RequireLockedClock) {
        // The native setter must snapshot the cached lease and sample time in
        // the same critical section, after any waiting monitor has renewed it.
        assert(pthread_mutex_trylock(&AudioMutex)==EBUSY);
    }
    return MockLease.now;
}
static bool ReadAudioNotificationValues(uint64_t &request,uint64_t &stamp,uint64_t &again) {
    if (CheckReadMutex) {assert(pthread_mutex_trylock(&AudioMutex)==0);pthread_mutex_unlock(&AudioMutex);}
    LeaseReads++;
    if (RemoveHostDuringRead) {RemoveHostDuringRead=false;CDV3AudioHost((void *)1,false);}
    if (NewHostDuringRead) {NewHostDuringRead=false;CDV3AudioHost((void *)2,true);}
    request=MockLease.request;
    if (RenewDuringRead) {MockLease.stamp=MockLease.now+2;MockLease.now+=3;RenewDuringRead=false;}
    stamp=MockLease.stamp;again=MockLease.coherent?request:request^1;
    return true;
}
static bool AudioPIDAlive(uint64_t) {
    if (CheckReadMutex) {assert(pthread_mutex_trylock(&AudioMutex)==0);pthread_mutex_unlock(&AudioMutex);}
    if (AdvanceDuringLiveness) MockLease.now+=AdvanceDuringLiveness;
    return MockLease.alive;
}
static void PublishAudioState(uint8_t bits) {
    if (CheckReadMutex) {assert(pthread_mutex_trylock(&AudioMutex)==0);pthread_mutex_unlock(&AudioMutex);}
    if (PublishedBits!=bits) {PublishedBits=bits;StateChanges++;}
}
static void MockSetter(bool value) {MockFlag=value?1:0;}
static void Reset(bool initial=false) {
    MockFlag=initial;AudioFlag=&MockFlag;NativeAudioSetter=MockSetter;
    AudioOwnHost=false;AudioForcing=false;AudioNativeWanted=false;AudioHostHelper=nullptr;AudioPendingHelper=nullptr;AudioPendingOrder=0;
    AudioCachedLease={};CheckReadMutex=true;LeaseReads=0;
    RequireLockedClock=false;RenewDuringRead=false;AdvanceDuringLiveness=0;
    PublishedBits=255;StateChanges=0;
    MockLease={((uint64_t)4242<<8)|1,10000,10001,true,true};
}
static unsigned MapCalls=0,MapCase=0;
static constexpr uintptr_t TestAddress=0x1eb12450cULL;
static kern_return_t MockRegion(vm_map_read_t,vm_address_t *address,vm_size_t *size,
    natural_t *depth,vm_region_recurse_info_t value,mach_msg_type_number_t *count) {
    assert(*address==TestAddress); // do not descend using the coarse map's start
    ++MapCalls;
    auto info=(vm_region_submap_info_64_t)value;
    if (MapCase==2) return KERN_INVALID_ADDRESS;
    *count=VM_REGION_SUBMAP_INFO_COUNT_64;
    *address=0x180000000ULL;*size=0x96000000ULL;
    info->protection=VM_PROT_READ;info->is_submap=*depth==0;
    if (MapCase==3) {*address=TestAddress+1;return KERN_SUCCESS;}
    if (MapCase==4) {*address=TestAddress;*size=8;return KERN_SUCCESS;}
    if (MapCase==5) {*count=0;return KERN_SUCCESS;}
    if (MapCase==6) {info->is_submap=1;return KERN_SUCCESS;}
    if (*depth) {
        *address=0x1e9ff0000ULL;*size=0x6dd4000ULL;
        info->is_submap=0;
        info->protection=VM_PROT_READ|(MapCase==1?0:VM_PROT_EXECUTE);
    }
    return KERN_SUCCESS;
}
}
int main() {
    assert(CDV3AudioMapped(TestAddress,16,VM_PROT_READ|VM_PROT_EXECUTE,MockRegion));assert(MapCalls==2);
    for (MapCase=1;MapCase<=6;MapCase++) {
        MapCalls=0;assert(!CDV3AudioMapped(TestAddress,16,VM_PROT_READ|VM_PROT_EXECUTE,MockRegion));
        assert(MapCalls<=64);
    }
    Reset();AudioTick();assert(!MockFlag && !AudioForcing); // live request alone has no authority
    assert(PublishedBits==8 && StateChanges==1);AudioTick();assert(StateChanges==1);
    CDV3AudioHost((void *)1,true);assert(MockFlag && AudioForcing);
    AudioTick();assert(PublishedBits==15 && StateChanges==2);
    unsigned before=LeaseReads;AudioSetter(false);assert(LeaseReads==before); // hook must never invoke notify
    AudioSetter(false);assert(MockFlag && !AudioNativeWanted);
    CDV3AudioHost((void *)1,false);assert(!MockFlag && !AudioForcing);
    AudioTick();assert(!MockFlag); // fresh heartbeat cannot override foreign host
    assert(PublishedBits==8);
    Reset(true);CDV3AudioHost((void *)1,true);MockLease.request=0;AudioTick();assert(MockFlag && !AudioForcing);
    Reset();CDV3AudioHost((void *)1,true);AudioSetter(true);MockLease.request=0;AudioTick();assert(MockFlag && !AudioForcing);
    Reset(true);CDV3AudioHost((void *)1,true);AudioSetter(false);MockLease.alive=false;AudioTick();assert(!MockFlag && !AudioForcing);
    Reset();CDV3AudioHost((void *)1,true);MockLease.now=18000;AudioTick();assert(MockFlag); // inclusive 8s boundary
    MockLease.now=18001;AudioTick();assert(!MockFlag && !AudioForcing);
    MockLease.stamp=18001;MockLease.now=18002;AudioTick();assert(!MockFlag && !AudioOwnHost);
    CDV3AudioHost((void *)1,true);assert(MockFlag && AudioForcing); // new session needs fresh identity observation
    Reset();CDV3AudioHost((void *)1,true);RenewDuringRead=true;AudioTick();
    assert(AudioCachedLease.stamp==10003 && AudioCachedLease.now==10004);
    assert(MockFlag && AudioForcing && AudioOwnHost && PublishedBits==15); // renew during read is not future
    Reset();CDV3AudioHost((void *)1,true);AdvanceDuringLiveness=8001;AudioTick();
    assert(!MockFlag && !AudioForcing && !AudioOwnHost); // expiry during read is still real expiry
    Reset();CDV3AudioHost((void *)1,true);
    // Simulate a monitor publishing a newer cached heartbeat while the setter
    // would be waiting for its lock. Clock instrumentation rejects the old
    // pre-lock sampling order even when thread scheduling would hide the race.
    MockLease.stamp=10003;MockLease.now=10004;AudioTick();
    RequireLockedClock=true;before=LeaseReads;AudioSetter(false);RequireLockedClock=false;
    assert(LeaseReads==before && MockFlag && AudioForcing && AudioOwnHost);
    MockLease.now=18004;RequireLockedClock=true;AudioSetter(false);RequireLockedClock=false;
    assert(!MockFlag && !AudioForcing && !AudioOwnHost); // cached lease still expires without IPC
    Reset();CDV3AudioHost((void *)1,true);MockLease.now=18001;
    before=LeaseReads;AudioSetter(false);assert(LeaseReads==before && !MockFlag && !AudioForcing); // cached lease ages without notify
    Reset();CDV3AudioHost((void *)1,true);CDV3AudioHost((void *)2,false);
    assert(MockFlag && AudioOwnHost); // unrelated helper cannot revoke our lease
    Reset();RemoveHostDuringRead=true;CDV3AudioHost((void *)1,true);
    assert(!MockFlag && !AudioOwnHost); // removal cancels an initial ownership read before publication
    Reset();CDV3AudioHost((void *)1,true);RemoveHostDuringRead=true;CDV3AudioHost((void *)2,true);
    assert(MockFlag && AudioOwnHost); // retiring helper1 cannot cancel helper2's pending claim
    CDV3AudioHost((void *)1,false);assert(MockFlag);CDV3AudioHost((void *)2,false);assert(!MockFlag);
    Reset();NewHostDuringRead=true;CDV3AudioHost((void *)1,true);
    CDV3AudioHost((void *)1,false);assert(MockFlag && AudioOwnHost); // late old publish must not replace helper2
    CDV3AudioHost((void *)2,false);assert(!MockFlag && !AudioOwnHost);
    Reset();
    AudioLease older={1,10000,10005,true,true,1},newer={1,10003,10004,true,true,2};
    pthread_mutex_lock(&AudioMutex);CacheAudioLeaseLocked(newer);CacheAudioLeaseLocked(older);pthread_mutex_unlock(&AudioMutex);
    assert(AudioCachedLease.stamp==10003); // completion time cannot order overlapping snapshots
    for (unsigned invalid=0;invalid<6;invalid++) {
        Reset();
        if (invalid==0) MockLease.stamp=0;
        if (invalid==1) MockLease.stamp=MockLease.now+1;
        if (invalid==2) MockLease.coherent=false;
        if (invalid==3) MockLease.request=((uint64_t)4242<<8)|2;
        if (invalid==4) MockLease.request=((uint64_t)1<<8)|1;
        if (invalid==5) MockLease.request=((uint64_t)INT_MAX+1)<<8|1;
        CDV3AudioHost((void *)1,true);assert(!MockFlag && !AudioForcing);
    }
    Reset(true);CDV3AudioHost((void *)1,true);MockFlag=0;AudioTick();assert(MockFlag && !AudioNativeWanted);
    MockLease.request=0;AudioTick();assert(!MockFlag); // native direct write preserved on exit
    Reset();AudioFlag=nullptr;CDV3AudioHost((void *)1,true);assert(!MockFlag && !AudioForcing);
    Reset();NativeAudioSetter=nullptr;CDV3AudioHost((void *)1,true);assert(!MockFlag && !AudioForcing);
    Reset();CDV3AudioHost((void *)1,true);CheckReadMutex=false; // other threads can hold the mutex during an outside read
    std::thread setters([]{for (int i=0;i<20000;i++) AudioSetter(i&1);});
    std::thread monitor([]{for (int i=0;i<20000;i++) AudioTick();});
    std::thread hosts([]{for (int i=0;i<20000;i++) CDV3AudioHost((void *)1,i&1);});
    setters.join();monitor.join();hosts.join();
    AudioSetter(false);CDV3AudioHost((void *)1,false);assert(!MockFlag && !AudioForcing);
    puts("Audio scope, intent restoration, lease expiry, invalid-request rejection, direct-write and concurrent-callback checks passed");
}
