// SPDX-License-Identifier: GPL-3.0-only
#include "NativeInventory.h"
#include <mach-o/loader.h>
#include <cstring>

namespace CDV3Inventory {
#define CD_INV_NAME(suffix) "com.cfluid.cardash.v3.inventory.v1." suffix
const char *const ChannelNames[ChannelCount]={
    CD_INV_NAME("snapshot"),CD_INV_NAME("cpu"),CD_INV_NAME("status"),
    CD_INV_NAME("aptransport.state"),CD_INV_NAME("aptransport.cpu"),
    CD_INV_NAME("aptransport.uuid0"),CD_INV_NAME("aptransport.uuid1"),
    CD_INV_NAME("mediaexperience.state"),CD_INV_NAME("mediaexperience.cpu"),
    CD_INV_NAME("mediaexperience.uuid0"),CD_INV_NAME("mediaexperience.uuid1"),
    CD_INV_NAME("airplaysender.state"),CD_INV_NAME("airplaysender.cpu"),
    CD_INV_NAME("airplaysender.uuid0"),CD_INV_NAME("airplaysender.uuid1"),
    CD_INV_NAME("failure")
};
#undef CD_INV_NAME
const char *const FrameworkPaths[FrameworkCount]={
    "/System/Library/PrivateFrameworks/APTransport.framework/APTransport",
    "/System/Library/PrivateFrameworks/MediaExperience.framework/MediaExperience",
    "/System/Library/PrivateFrameworks/AirPlaySender.framework/AirPlaySender"
};

static Identity InvalidIdentity(uint32_t error,uint32_t type=0,uint32_t subtype=0) {
    Identity result;result.state=Invalid;result.error=error;
    result.cpuType=type;result.cpuSubtype=subtype;return result;
}

Identity ParseIdentity(const void *bytes,size_t length) {
    if(!bytes || length<sizeof(mach_header_64))return InvalidIdentity(TruncatedHeader);
    mach_header_64 header={};memcpy(&header,bytes,sizeof(header));
    if(header.magic!=MH_MAGIC_64)return InvalidIdentity(InvalidMagic);
    uint32_t type=(uint32_t)header.cputype,subtype=(uint32_t)header.cpusubtype;
    if(header.ncmds>MaxCommands || header.sizeofcmds>MaxCommandBytes)
        return InvalidIdentity(CommandLimit,type,subtype);
    if(header.sizeofcmds>length-sizeof(header))return InvalidIdentity(TruncatedCommands,type,subtype);
    const uint8_t *commands=(const uint8_t *)bytes+sizeof(header);
    size_t position=0;bool found=false;uint8_t uuid[16]={};
    for(uint32_t index=0;index<header.ncmds;index++) {
        if(header.sizeofcmds-position<sizeof(load_command))return InvalidIdentity(InvalidCommand,type,subtype);
        load_command command={};memcpy(&command,commands+position,sizeof(command));
        if(command.cmdsize<sizeof(command) || (command.cmdsize&7) || command.cmdsize>header.sizeofcmds-position)
            return InvalidIdentity(InvalidCommand,type,subtype);
        if(command.cmd==LC_UUID) {
            if(command.cmdsize!=sizeof(uuid_command))return InvalidIdentity(InvalidUUIDCommand,type,subtype);
            if(found)return InvalidIdentity(DuplicateUUID,type,subtype);
            uuid_command value={};memcpy(&value,commands+position,sizeof(value));
            memcpy(uuid,value.uuid,sizeof(uuid));found=true;
        }
        position+=command.cmdsize;
    }
    if(position!=header.sizeofcmds)return InvalidIdentity(CommandLengthMismatch,type,subtype);
    if(!found)return InvalidIdentity(MissingUUID,type,subtype);
    Identity result;result.state=Observed;result.cpuType=type;result.cpuSubtype=subtype;
    for(unsigned index=0;index<8;index++) {
        result.uuid0=(result.uuid0<<8)|uuid[index];
        result.uuid1=(result.uuid1<<8)|uuid[index+8];
    }
    return result;
}

int FrameworkIndex(const char *path) {
    if(path)for(size_t index=0;index<FrameworkCount;index++)
        if(strcmp(path,FrameworkPaths[index])==0)return (int)index;
    return -1;
}
uint64_t PackCPU(uint32_t type,uint32_t subtype){return ((uint64_t)type<<32)|subtype;}
uint64_t PackState(const Identity &identity){return ((uint64_t)identity.error<<32)|identity.state;}
uint64_t PackFailure(uint32_t pid,uint8_t phase,size_t channel,uint32_t status) {
    return ((uint64_t)pid<<32)|((uint64_t)phase<<24)|((uint64_t)(channel&0xff)<<16)|(status&0xffff);
}

bool Publisher::initialize(uint32_t pid,Operations operations) {
    if(initialized_)return registered_ && pid==pid_;
    initialized_=true;pid_=pid;operations_=operations;
    for(size_t index=0;index<ChannelCount;index++)tokens_[index]=-1;
    if(!pid || !operations.registerCheck || !operations.setState)return false;
    registered_=true;
    for(size_t index=0;index<ChannelCount;index++) {
        uint32_t status=operations_.registerCheck(operations_.context,ChannelNames[index],&tokens_[index]);
        if(status) {
            tokens_[index]=-1;
            if(registered_){registerError_=status;registerChannel_=index;}
            registered_=false;
            if(operations_.logFailure)operations_.logFailure(operations_.context,RegisterPhase,index,status);
        }
    }
    return registered_;
}

void Publisher::failure(uint8_t phase,size_t channel,uint32_t status) {
    if(tokens_[FailureChannel]<0 || !operations_.setState)return;
    uint32_t result=operations_.setState(operations_.context,tokens_[FailureChannel],PackFailure(pid_,phase,channel,status));
    if(result && operations_.logFailure)
        operations_.logFailure(operations_.context,PayloadPhase,FailureChannel,result);
}
bool Publisher::write(size_t channel,uint64_t value,uint8_t phase) {
    if(tokens_[channel]<0)return false;
    uint32_t status=operations_.setState(operations_.context,tokens_[channel],value);
    if(!status)return true;
    if(operations_.logFailure)operations_.logFailure(operations_.context,phase,channel,status);
    // One best-effort failure sideband, never an unbounded retry.
    if(channel!=FailureChannel)failure(phase,channel,status);
    return false;
}
bool Publisher::publish(const Snapshot &snapshot) {
    if(!initialized_ || !pid_ || !operations_.setState)return false;
    if(sequence_>=0xfffffffc)sequence_=0;
    sequence_+=2;
    bool began=write(SnapshotChannel,((uint64_t)pid_<<32)|(sequence_-1),BeginPhase);
    if(!registered_){failure(RegisterPhase,registerChannel_,registerError_);return false;}
    if(!began)return false;
    uint64_t values[ChannelCount]={};
    values[CPUChannel]=PackCPU(snapshot.cpuType,snapshot.cpuSubtype);
    values[StatusChannel]=((uint64_t)snapshot.adapterError<<32)|snapshot.flags;
    for(size_t index=0;index<FrameworkCount;index++) {
        size_t base=APState+4*index;const Identity &identity=snapshot.frameworks[index];
        values[base]=PackState(identity);values[base+1]=PackCPU(identity.cpuType,identity.cpuSubtype);
        if(identity.state==Observed && identity.error==NoError) {
            values[base+2]=identity.uuid0;values[base+3]=identity.uuid1;
        }
    }
    for(size_t index=CPUChannel;index<FailureChannel;index++)
        if(!write(index,values[index],PayloadPhase))return false;
    if(!write(FailureChannel,0,PayloadPhase))return false;
    return write(SnapshotChannel,((uint64_t)pid_<<32)|sequence_,CommitPhase);
}
}

#ifndef CDV3_INVENTORY_TEST
#import <Foundation/Foundation.h>
#include "AudioVM.h"
#include <mach-o/dyld.h>
#include <dlfcn.h>
#include <notify.h>
#include <pthread.h>
#include <unistd.h>

namespace {
using namespace CDV3Inventory;
static Snapshot Current;
static const mach_header *FrameworkHeaders[FrameworkCount]={};
static pthread_mutex_t InventoryLock=PTHREAD_MUTEX_INITIALIZER;
static dispatch_source_t InventorySource;
static Publisher InventoryPublisher;

static Identity LoadedIdentity(const mach_header *raw) {
    if(!raw || !CDV3AudioMapped((uintptr_t)raw,sizeof(mach_header_64),VM_PROT_READ))
        return InvalidIdentity(UnreadableMapping);
    mach_header_64 header={};memcpy(&header,raw,sizeof(header));
    if(header.magic!=MH_MAGIC_64)return InvalidIdentity(InvalidMagic);
    if(header.ncmds>MaxCommands || header.sizeofcmds>MaxCommandBytes)
        return InvalidIdentity(CommandLimit,(uint32_t)header.cputype,(uint32_t)header.cpusubtype);
    size_t length=sizeof(header)+header.sizeofcmds;
    if(!CDV3AudioMapped((uintptr_t)raw,length,VM_PROT_READ))
        return InvalidIdentity(UnreadableMapping,(uint32_t)header.cputype,(uint32_t)header.cpusubtype);
    return ParseIdentity(raw,length);
}
static void Changed(){if(InventorySource)dispatch_source_merge_data(InventorySource,1);}
static void AddedImage(const mach_header *header,intptr_t slide) {
    (void)slide;Dl_info info={};
    if(!dladdr(header,&info))return;
    int index=FrameworkIndex(info.dli_fname);if(index<0)return;
    Identity observed=LoadedIdentity(header);
    pthread_mutex_lock(&InventoryLock);
    if(FrameworkHeaders[index] && FrameworkHeaders[index]!=header) {
        Current.frameworks[index]=Identity{};Current.frameworks[index].state=Ambiguous;
    } else if(Current.frameworks[index].state!=Ambiguous) {
        FrameworkHeaders[index]=header;Current.frameworks[index]=observed;
    }
    pthread_mutex_unlock(&InventoryLock);Changed();
}
static void RemovedImage(const mach_header *header,intptr_t slide) {
    (void)slide;bool changed=false;
    pthread_mutex_lock(&InventoryLock);
    for(size_t index=0;index<FrameworkCount;index++)if(FrameworkHeaders[index]==header) {
        FrameworkHeaders[index]=nullptr;
        // If duplicate exact-path images were observed, do not guess which survives.
        if(Current.frameworks[index].state!=Ambiguous)Current.frameworks[index]=Identity{};
        changed=true;
    }
    pthread_mutex_unlock(&InventoryLock);if(changed)Changed();
}
static uint32_t RegisterChannel(void *,const char *name,int *token){return notify_register_check(name,token);}
static uint32_t SetChannel(void *,int token,uint64_t value){return notify_set_state(token,value);}
static void LogFailure(void *,uint8_t phase,size_t channel,uint32_t status) {
    NSLog(@"CarDash V3 inventory notify failure phase=%u channel=%s status=%u",phase,ChannelNames[channel],status);
}
__attribute__((constructor)) static void StartInventory() {
    @autoreleasepool {
        if(![[NSProcessInfo processInfo].processName isEqualToString:@"mediaserverd"])return;
        Current.flags=ConstructorEntered;
        Dl_info info={};Identity own;
        // An address in this dylib's data avoids function-pointer PAC handling.
        if(dladdr((const void *)&Current,&info) && info.dli_fbase)
            own=LoadedIdentity((const mach_header *)info.dli_fbase);
        else own=InvalidIdentity(MissingOwnImage);
        Current.cpuType=own.cpuType;Current.cpuSubtype=own.cpuSubtype;Current.adapterError=own.error;
        if(own.state==Observed)Current.flags|=AdapterParsed;
        else NSLog(@"CarDash V3 inventory adapter identity error=%u",own.error);
        dispatch_queue_t queue=dispatch_queue_create("com.cfluid.cardash.v3.inventory",DISPATCH_QUEUE_SERIAL);
        if(!queue){NSLog(@"CarDash V3 inventory could not create reporting queue");return;}
        InventorySource=dispatch_source_create(DISPATCH_SOURCE_TYPE_DATA_ADD,0,0,queue);
        if(!InventorySource){NSLog(@"CarDash V3 inventory could not create reporting source");return;}
        dispatch_source_set_event_handler(InventorySource,^{
            @autoreleasepool {
                // Never enter notify/dyld while holding the snapshot lock.
                Snapshot snapshot;pthread_mutex_lock(&InventoryLock);snapshot=Current;pthread_mutex_unlock(&InventoryLock);
                InventoryPublisher.initialize((uint32_t)getpid(),{nullptr,RegisterChannel,SetChannel,LogFailure});
                InventoryPublisher.publish(snapshot);
            }
        });
        dispatch_resume(InventorySource);
        _dyld_register_func_for_add_image(AddedImage);
        _dyld_register_func_for_remove_image(RemovedImage);
        pthread_mutex_lock(&InventoryLock);Current.flags|=InitialScanComplete;pthread_mutex_unlock(&InventoryLock);
        Changed();
    }
}
}
#endif
