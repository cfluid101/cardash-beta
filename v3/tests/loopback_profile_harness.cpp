#include "../native/LoopbackProfile.h"
#include <cassert>
#include <cstdio>
#include <vector>

static uintptr_t deniedAddress=0;
static unsigned mappingCalls=0;
static bool Mapping(uintptr_t address,size_t bytes) {
    ++mappingCalls;assert(bytes==20);return address!=deniedAddress;
}

int main() {
    using namespace CDV3Loopback;
    // Independent firmware bytes, including each PACIBSP, from the matched
    // APTransport image retained in the 20A357 research evidence.
    const uint8_t targetUUID[]={0x5e,0x0e,0x47,0x3a,0x63,0xec,0x32,0x93,0xa0,0x97,0xee,0xad,0x34,0x5a,0x82,0x44};
    const uint8_t update[]={0x7f,0x23,0x03,0xd5,0xe9,0x23,0xb9,0x6d,0xfc,0x6f,0x01,0xa9,0xfa,0x67,0x02,0xa9,0xf8,0x5f,0x03,0xa9};
    const uint8_t event[]={0x7f,0x23,0x03,0xd5,0xff,0x83,0x02,0xd1,0xe9,0x23,0x04,0x6d,0xfa,0x67,0x05,0xa9,0xf8,0x5f,0x06,0xa9};
    auto target=SelectProfile(targetUUID,0x0100000c,0x80000002);
    assert(target && target->guardedLayout && target->updateOffset==0x5aeec && target->eventOffset==0x5dec0);
    assert(MatchEntries(*target,update,sizeof(update),event,sizeof(event)));
    assert(!SelectProfile(targetUUID,0x0100000c,0));
    assert(!SelectProfile(targetUUID,0x0100000c,2)); // exact subtype/capability identity required
    assert(!SelectProfile(targetUUID,0x01000007,0x80000002));
    assert(!SelectProfile(nullptr,0x0100000c,0x80000002));
    uint8_t unknown[16];memcpy(unknown,targetUUID,sizeof(unknown));unknown[0]^=1;
    assert(!SelectProfile(unknown,0x0100000c,0x80000002));
    assert(!MatchEntries(*target,update+4,sizeof(update)-4,event,sizeof(event)));
    assert(!MatchEntries(*target,update,sizeof(update),event+4,sizeof(event)-4));
    for(size_t i=0;i<sizeof(update);i++) {
        uint8_t changed[sizeof(update)];memcpy(changed,update,sizeof(changed));changed[i]^=1;
        assert(!MatchEntries(*target,changed,sizeof(changed),event,sizeof(event)));
        memcpy(changed,event,sizeof(changed));changed[i]^=1;
        assert(!MatchEntries(*target,update,sizeof(update),changed,sizeof(changed)));
    }
    for(size_t n=0;n<sizeof(update);n++) {
        assert(!MatchEntries(*target,update,n,event,sizeof(event)));
        assert(!MatchEntries(*target,update,sizeof(update),event,n));
    }
    std::vector<uint8_t> image(0x60000);
    memcpy(image.data()+target->updateOffset,update,sizeof(update));
    memcpy(image.data()+target->eventOffset,event,sizeof(event));
    uintptr_t base=(uintptr_t)image.data();
    bool mappingRejected=true;
    assert(MappedEntriesMatch(*target,base,image.size(),Mapping,&mappingRejected) && mappingCalls==2 && !mappingRejected);
    mappingCalls=0;deniedAddress=base+target->updateOffset;
    assert(!MappedEntriesMatch(*target,base,image.size(),Mapping,&mappingRejected) && mappingCalls==1 && mappingRejected);
    mappingCalls=0;deniedAddress=base+target->eventOffset;
    assert(!MappedEntriesMatch(*target,base,image.size(),Mapping) && mappingCalls==2);
    mappingCalls=0;deniedAddress=0;
    assert(!MappedEntriesMatch(*target,base,target->eventOffset+19,Mapping) && !mappingCalls);
    assert(!MappedEntriesMatch(*target,UINTPTR_MAX-target->updateOffset+1,image.size(),Mapping) && !mappingCalls);
    assert(!MappedEntriesMatch(*target,base,image.size(),nullptr));
    image[target->eventOffset]^=1;mappingRejected=true;
    assert(!MappedEntriesMatch(*target,base,image.size(),Mapping,&mappingRejected) && !mappingRejected);
    const uint8_t legacyUUID[]={0xbc,0xc4,0x74,0xf5,0x27,0x45,0x36,0x52,0x99,0x5f,0xa0,0x6f,0x65,0x0f,0x76,0xfc};
    auto legacy=SelectProfile(legacyUUID,0x0100000c,0);
    assert(legacy && !legacy->guardedLayout && legacy->updateOffset==0x55430 && legacy->eventOffset==0x57ec4);
    assert(legacy->prologueSize==16 && MatchEntries(*legacy,update+4,16,event+4,16));
    assert(!MatchEntries(*legacy,update,20,event,20));
    puts("Exact identity and full prologue gates passed");
}
