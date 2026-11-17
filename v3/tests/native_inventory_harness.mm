#include "../native/NativeInventory.h"
#include <mach-o/loader.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <utility>
using namespace CDV3Inventory;

static std::vector<uint8_t> Image(uint32_t subtype=0x80000002) {
    mach_header_64 h={};h.magic=MH_MAGIC_64;h.cputype=0x0100000c;
    h.cpusubtype=subtype;h.filetype=MH_DYLIB;h.ncmds=1;h.sizeofcmds=sizeof(uuid_command);
    uuid_command u={};u.cmd=LC_UUID;u.cmdsize=sizeof(u);
    for(unsigned i=0;i<16;i++)u.uuid[i]=(uint8_t)(i+1);
    std::vector<uint8_t> result(sizeof(h)+sizeof(u));
    memcpy(result.data(),&h,sizeof(h));memcpy(result.data()+sizeof(h),&u,sizeof(u));return result;
}
static mach_header_64 Header(const std::vector<uint8_t> &data) {
    mach_header_64 h={};memcpy(&h,data.data(),sizeof(h));return h;
}
static void SetHeader(std::vector<uint8_t> &data,mach_header_64 h) {memcpy(data.data(),&h,sizeof(h));}
struct FakeNotify {
    unsigned registrations=0, failures=0;
    int failRegistration=-1, failWrite=-1, failWriteAfter=0;
    uint32_t error=7;
    bool failOnce=true;
    std::vector<std::pair<int,uint64_t>> writes;
    uint64_t values[ChannelCount]={};
    static uint32_t Register(void *context,const char *name,int *token) {
        auto &self=*(FakeNotify *)context;unsigned index=self.registrations++;
        assert(index<ChannelCount && !strcmp(name,ChannelNames[index]));
        if((int)index==self.failRegistration)return self.error;
        *token=(int)index;return 0;
    }
    static uint32_t Write(void *context,int token,uint64_t value) {
        auto &self=*(FakeNotify *)context;assert(token>=0 && token<(int)ChannelCount);
        self.writes.push_back({token,value});
        if(token==self.failWrite) {
            if(self.failWriteAfter>0)self.failWriteAfter--;
            else {if(self.failOnce)self.failWrite=-1;return self.error;}
        }
        self.values[token]=value;return 0;
    }
    static void Log(void *context,uint8_t phase,size_t channel,uint32_t status) {
        auto &self=*(FakeNotify *)context;self.failures++;
        assert(phase>=RegisterPhase && phase<=CommitPhase && channel<ChannelCount && status==self.error);
    }
    Operations operations(){return {this,Register,Write,Log};}
};

int main() {
    auto image=Image();auto parsed=ParseIdentity(image.data(),image.size());
    assert(parsed.state==Observed && parsed.error==NoError);
    assert(parsed.cpuType==0x0100000c && parsed.cpuSubtype==0x80000002);
    assert(parsed.uuid0==0x0102030405060708ULL && parsed.uuid1==0x090a0b0c0d0e0f10ULL);
    assert(PackCPU(parsed.cpuType,parsed.cpuSubtype)==0x0100000c80000002ULL);
    assert(ParseIdentity(nullptr,0).error==TruncatedHeader);
    assert(ParseIdentity(image.data(),sizeof(mach_header_64)-1).error==TruncatedHeader);
    auto malformed=image;auto h=Header(malformed);h.magic=MH_CIGAM_64;SetHeader(malformed,h);
    assert(ParseIdentity(malformed.data(),malformed.size()).error==InvalidMagic);
    malformed=image;h=Header(malformed);h.ncmds=MaxCommands+1;SetHeader(malformed,h);
    assert(ParseIdentity(malformed.data(),malformed.size()).error==CommandLimit);
    malformed=image;h=Header(malformed);h.sizeofcmds=MaxCommandBytes+1;SetHeader(malformed,h);
    assert(ParseIdentity(malformed.data(),malformed.size()).error==CommandLimit);
    assert(ParseIdentity(image.data(),image.size()-1).error==TruncatedCommands);
    // memcpy-based parsing must also accept an unaligned input buffer.
    std::vector<uint8_t> unaligned(1,0);unaligned.insert(unaligned.end(),image.begin(),image.end());
    assert(ParseIdentity(unaligned.data()+1,image.size()).uuid0==parsed.uuid0);
    for(uint32_t size:{0u,4u,9u,0xfffffff8u}) {
        malformed=image;memcpy(malformed.data()+sizeof(mach_header_64)+4,&size,4);
        assert(ParseIdentity(malformed.data(),malformed.size()).error==InvalidCommand);
    }
    malformed=image;uint32_t size=16;memcpy(malformed.data()+sizeof(mach_header_64)+4,&size,4);
    assert(ParseIdentity(malformed.data(),malformed.size()).error==InvalidUUIDCommand);
    malformed=image;malformed.insert(malformed.end(),image.begin()+sizeof(mach_header_64),image.end());
    h=Header(malformed);h.ncmds=2;h.sizeofcmds=2*sizeof(uuid_command);SetHeader(malformed,h);
    assert(ParseIdentity(malformed.data(),malformed.size()).error==DuplicateUUID);
    malformed=image;h=Header(malformed);h.ncmds=0;h.sizeofcmds=0;SetHeader(malformed,h);
    assert(ParseIdentity(malformed.data(),malformed.size()).error==MissingUUID);
    malformed=image;h=Header(malformed);h.ncmds=0;SetHeader(malformed,h);
    assert(ParseIdentity(malformed.data(),malformed.size()).error==CommandLengthMismatch);
    malformed=image;h=Header(malformed);h.ncmds=2;SetHeader(malformed,h);
    auto truncatedCommand=ParseIdentity(malformed.data(),malformed.size());
    assert(truncatedCommand.error==InvalidCommand && truncatedCommand.uuid0==0 && truncatedCommand.uuid1==0);
    assert(FrameworkIndex(FrameworkPaths[0])==0 && FrameworkIndex(FrameworkPaths[1])==1 && FrameworkIndex(FrameworkPaths[2])==2);
    assert(FrameworkIndex(nullptr)==-1 && FrameworkIndex("/tmp/APTransport.framework/APTransport")==-1);
    assert(FrameworkIndex("/System/Library/PrivateFrameworks/APTransport.framework/APTransport.bad")==-1);

    Snapshot snapshot;snapshot.flags=ConstructorEntered|InitialScanComplete|AdapterParsed;
    snapshot.cpuType=parsed.cpuType;snapshot.cpuSubtype=parsed.cpuSubtype;snapshot.frameworks[0]=parsed;
    snapshot.frameworks[1].state=Invalid;snapshot.frameworks[1].error=MissingUUID;
    FakeNotify io;Publisher publisher;assert(publisher.initialize(123,io.operations()));
    assert(publisher.initialize(123,io.operations()) && io.registrations==ChannelCount);
    assert(publisher.publish(snapshot));
    assert(io.writes.front()==std::make_pair((int)SnapshotChannel,(123ULL<<32)|1));
    assert(io.writes.back()==std::make_pair((int)SnapshotChannel,(123ULL<<32)|2));
    assert(io.values[CPUChannel]==0x0100000c80000002ULL && io.values[StatusChannel]==7);
    assert(io.values[APState]==1 && io.values[APUUID0]==parsed.uuid0 && io.values[APUUID1]==parsed.uuid1);
    assert(io.values[MediaState]==((uint64_t)MissingUUID<<32|Invalid));
    assert(io.values[AirState]==NotObserved && io.values[FailureChannel]==0);
    assert(publisher.publish(snapshot) && io.values[SnapshotChannel]==((123ULL<<32)|4));
    io.failWrite=APUUID0;assert(!publisher.publish(snapshot));
    assert((io.values[SnapshotChannel]&1)==1);
    assert(io.values[FailureChannel]==PackFailure(123,PayloadPhase,APUUID0,io.error));
    assert(io.failures==1);
    assert(publisher.publish(snapshot));assert(!(io.values[SnapshotChannel]&1) && io.values[FailureChannel]==0);

    FakeNotify badRegistration;badRegistration.failRegistration=MediaState;
    Publisher missing;assert(!missing.initialize(456,badRegistration.operations()));
    assert(!missing.publish(snapshot));assert((badRegistration.values[SnapshotChannel]&1)==1);
    assert(badRegistration.values[FailureChannel]==PackFailure(456,RegisterPhase,MediaState,badRegistration.error));
    assert(badRegistration.registrations==ChannelCount);
    assert(!missing.initialize(456,badRegistration.operations()) && badRegistration.registrations==ChannelCount);
    FakeNotify failedBegin;Publisher begin;assert(begin.initialize(789,failedBegin.operations()));
    failedBegin.failWrite=SnapshotChannel;assert(!begin.publish(snapshot));
    assert(failedBegin.values[SnapshotChannel]==0);
    assert(failedBegin.values[FailureChannel]==PackFailure(789,BeginPhase,SnapshotChannel,failedBegin.error));
    FakeNotify failedCommit;Publisher commit;assert(commit.initialize(890,failedCommit.operations()));
    failedCommit.failWrite=SnapshotChannel;failedCommit.failWriteAfter=1;
    assert(!commit.publish(snapshot) && (failedCommit.values[SnapshotChannel]&1));
    assert(failedCommit.values[FailureChannel]==PackFailure(890,CommitPhase,SnapshotChannel,failedCommit.error));
    assert(failedCommit.failures==1);
    // If the sideband cannot be cleared, the payload must remain uncommitted.
    FakeNotify failedSideband;Publisher sideband;assert(sideband.initialize(891,failedSideband.operations()));
    failedSideband.failWrite=FailureChannel;
    assert(!sideband.publish(snapshot) && (failedSideband.values[SnapshotChannel]&1));
    assert(failedSideband.failures==1);
    // An invalid observation must never leak a previous valid UUID.
    Snapshot invalid=snapshot;invalid.frameworks[0].state=Ambiguous;
    assert(publisher.publish(invalid));
    assert(io.values[APState]==Ambiguous && io.values[APUUID0]==0 && io.values[APUUID1]==0);
    Publisher noPID;FakeNotify invalidPID;assert(!noPID.initialize(0,invalidPID.operations()));
    assert(!noPID.publish(snapshot) && invalidPID.registrations==0 && invalidPID.writes.empty());
    // Unsupported/missing observations never turn into readiness flags.
    Snapshot missingImages;missingImages.flags=ConstructorEntered|InitialScanComplete;
    FakeNotify absent;Publisher noImages;assert(noImages.initialize(222,absent.operations()));
    assert(noImages.publish(missingImages));assert(absent.values[APState]==0 && absent.values[MediaState]==0 && absent.values[AirState]==0);
    puts("Native inventory parser and publication checks passed");
}
