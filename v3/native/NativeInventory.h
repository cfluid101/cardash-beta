// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstddef>
#include <cstdint>

// Diagnostic-only protocol. These observations never authorize a hook/session.
// Read snapshot/failure before and after the body; accept only an unchanged,
// nonzero even snapshot, zero failure and a live publisher PID.
namespace CDV3Inventory {
constexpr size_t FrameworkCount=3, ChannelCount=16;
constexpr uint32_t MaxCommands=4096, MaxCommandBytes=1024*1024;
enum Channel : size_t { SnapshotChannel=0, CPUChannel=1, StatusChannel=2,
    APState=3, APCPU=4, APUUID0=5, APUUID1=6,
    MediaState=7, MediaCPU=8, MediaUUID0=9, MediaUUID1=10,
    AirState=11, AirCPU=12, AirUUID0=13, AirUUID1=14, FailureChannel=15 };
extern const char *const ChannelNames[ChannelCount];
extern const char *const FrameworkPaths[FrameworkCount];
enum State : uint32_t { NotObserved=0, Observed=1, Invalid=2, Ambiguous=3 };
enum ParseError : uint32_t { NoError=0, TruncatedHeader=1, InvalidMagic=2,
    CommandLimit=3, TruncatedCommands=4, InvalidCommand=5,
    InvalidUUIDCommand=6, DuplicateUUID=7, MissingUUID=8,
    CommandLengthMismatch=9, UnreadableMapping=10, MissingOwnImage=11 };
enum Flag : uint32_t { ConstructorEntered=1, InitialScanComplete=2, AdapterParsed=4 };
enum Phase : uint8_t { RegisterPhase=1, BeginPhase=2, PayloadPhase=3, CommitPhase=4 };

struct Identity {
    uint32_t state=NotObserved, error=NoError, cpuType=0, cpuSubtype=0;
    uint64_t uuid0=0, uuid1=0;
};
struct Snapshot {
    uint32_t flags=0, adapterError=NoError, cpuType=0, cpuSubtype=0;
    Identity frameworks[FrameworkCount];
};
struct Operations {
    void *context=nullptr;
    uint32_t (*registerCheck)(void *,const char *,int *)=nullptr;
    uint32_t (*setState)(void *,int,uint64_t)=nullptr;
    void (*logFailure)(void *,uint8_t,size_t,uint32_t)=nullptr;
};

Identity ParseIdentity(const void *bytes,size_t length);
int FrameworkIndex(const char *path);
uint64_t PackCPU(uint32_t type,uint32_t subtype);
uint64_t PackState(const Identity &identity);
uint64_t PackFailure(uint32_t pid,uint8_t phase,size_t channel,uint32_t status);

class Publisher {
public:
    bool initialize(uint32_t pid,Operations operations);
    bool publish(const Snapshot &snapshot);
private:
    uint32_t pid_=0, sequence_=0;
    int tokens_[ChannelCount]={};
    Operations operations_;
    bool initialized_=false, registered_=false;
    uint32_t registerError_=0;
    size_t registerChannel_=0;
    bool write(size_t channel,uint64_t value,uint8_t phase);
    void failure(uint8_t phase,size_t channel,uint32_t status);
};
}
