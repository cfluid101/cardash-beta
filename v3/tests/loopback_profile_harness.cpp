#include "../native/LoopbackProfile.h"
#include <cassert>
#include <cstdio>
#include <vector>
#include <cstdlib>

static uintptr_t deniedAddress=0;
static unsigned mappingCalls=0;
static bool Mapping(uintptr_t address,size_t bytes) {
    ++mappingCalls;assert(bytes==20);return address!=deniedAddress;
}

static void Verify1541Profile() {
    using namespace CDV3Loopback;
    // Literal fixtures come from iPhone14,2 / 19E258 cache disassembly,
    // not the production table. In particular its event prologue differs.
    const uint8_t uuid[]={0x5a,0x56,0x59,0x81,0x1c,0x87,0x39,0x34,0x97,0xcc,0x5f,0x55,0x41,0xbc,0x43,0x8f};
    const uint8_t update[]={0x7f,0x23,0x03,0xd5,0xe9,0x23,0xb9,0x6d,0xfc,0x6f,0x01,0xa9,0xfa,0x67,0x02,0xa9,0xf8,0x5f,0x03,0xa9};
    const uint8_t event[]={0x7f,0x23,0x03,0xd5,0xff,0x03,0x02,0xd1,0xe9,0x23,0x03,0x6d,0xf8,0x5f,0x04,0xa9,0xf6,0x57,0x05,0xa9};
    const auto *profile=SelectProfile(uuid,0x0100000c,0x80000002);
    assert(profile && "15.4.1 APTransport profile missing");
    assert(profile->guardedLayout);
    assert(!SelectProfile(uuid,0x0100000c,0));
    assert(!SelectProfile(uuid,0x0100000c,2));
    assert(!SelectProfile(uuid,0x01000007,0x80000002));
    uint8_t foreign[16];memcpy(foreign,uuid,sizeof(foreign));foreign[15]^=1;
    assert(!SelectProfile(foreign,0x0100000c,0x80000002));
    // Populate the independent image coordinates. A wrong table offset must
    // fail the real entry gate, even when its fingerprint is otherwise right.
    std::vector<uint8_t> image(0x60000);
    memcpy(image.data()+0x5a05c,update,sizeof(update));
    memcpy(image.data()+0x5d1f0,event,sizeof(event));
    uintptr_t base=(uintptr_t)image.data();
    bool mappingRejected=true;mappingCalls=0;deniedAddress=0;
    assert(MappedEntriesMatch(*profile,base,image.size(),Mapping,&mappingRejected));
    assert(mappingCalls==2 && !mappingRejected);
    for(uintptr_t entry:{base+0x5a05c,base+0x5d1f0}) {
        deniedAddress=entry;mappingCalls=0;mappingRejected=false;
        assert(!MappedEntriesMatch(*profile,base,image.size(),Mapping,&mappingRejected) && mappingRejected);
    }
    deniedAddress=0;mappingCalls=0;
    assert(!MappedEntriesMatch(*profile,base,0x5d1f0+19,Mapping) && !mappingCalls);
    assert(!MappedEntriesMatch(*profile,UINTPTR_MAX-0x5a05c+1,image.size(),Mapping) && !mappingCalls);
    for(size_t entry:{size_t(0x5a05c),size_t(0x5d1f0)}) {
        for(size_t i=0;i<20;i++) {
            image[entry+i]^=1;mappingRejected=true;
            assert(!MappedEntriesMatch(*profile,base,image.size(),Mapping,&mappingRejected) && !mappingRejected);
            image[entry+i]^=1;
        }
    }
    assert(!MatchEntries(*profile,update+4,sizeof(update)-4,event,sizeof(event)));
    assert(!MatchEntries(*profile,update,sizeof(update),event+4,sizeof(event)-4));
    puts("19E258 guarded arm64e entries reject wrong CPU, mappings and instructions");
}

static unsigned Nibble(char c) {
    if(c>='0' && c<='9')return c-'0';
    if(c>='a' && c<='f')return c-'a'+10;
    if(c>='A' && c<='F')return c-'A'+10;
    assert(false);return 0;
}
static std::vector<uint8_t> Hex(const char *text) {
    std::vector<uint8_t> result;assert(strlen(text)%2==0);
    while(*text){result.push_back((Nibble(text[0])<<4)|Nibble(text[1]));text+=2;}
    return result;
}
static void VerifyFixture(char **arg) {
    using namespace CDV3Loopback;
    const auto uuid=Hex(arg[1]),update=Hex(arg[6]),event=Hex(arg[7]);
    const uint32_t cpu=(uint32_t)strtoul(arg[2],nullptr,0),sub=(uint32_t)strtoul(arg[3],nullptr,0);
    const size_t updateOffset=strtoull(arg[4],nullptr,0),eventOffset=strtoull(arg[5],nullptr,0);
    assert(uuid.size()==16 && update.size()==20 && event.size()==20);
    const auto profile=SelectProfile(uuid.data(),cpu,sub);
    assert(profile && profile->guardedLayout);
    assert(AdapterMatches(*profile,sub==0x80000002));
    assert(!AdapterMatches(*profile,sub!=0x80000002));
    assert(CanHook(*profile)==bool(atoi(arg[9])));
    assert(!SelectProfile(uuid.data(),0x1000007,sub));
    assert(!SelectProfile(uuid.data(),cpu,sub^0x80000002));
    auto wrong=uuid;wrong[0]^=1;assert(!SelectProfile(wrong.data(),cpu,sub));
    assert(!strcmp(LayoutName(profile->layout),arg[8]));
    const auto layout=LayoutFor(profile->layout);
    if(profile->layout==LayoutFamily::RequestIdentifier) {
        assert(layout.hostTime==0xb8 && layout.selectedTransport==0xc0 && layout.selectedInterface==0xd0 && layout.stateSize==0xd8 && layout.requestIdentifier==0xb0);
    } else if(profile->layout==LayoutFamily::Middle) {
        assert(layout.hostTime==0xb0 && layout.selectedTransport==0xb8 && layout.selectedInterface==0xc8 && layout.stateSize==0xd0 && !layout.requestIdentifier);
    } else {
        assert(!CanHook(*profile) && layout.hostTime==0xb0 && !layout.selectedTransport && layout.selectedInterface==0xc0);
    }
    std::vector<uint8_t> image(eventOffset+64);
    memcpy(image.data()+updateOffset,update.data(),20);memcpy(image.data()+eventOffset,event.data(),20);
    const auto base=(uintptr_t)image.data();mappingCalls=0;deniedAddress=0;
    assert(MappedEntriesMatch(*profile,base,image.size(),Mapping) && mappingCalls==2);
    bool mappingRejected=false;
    deniedAddress=base+eventOffset;
    assert(!MappedEntriesMatch(*profile,base,image.size(),Mapping,&mappingRejected) && mappingRejected);
    deniedAddress=0;
    assert(!MappedEntriesMatch(*profile,base,eventOffset+19,Mapping));
    assert(!MappedEntriesMatch(*profile,UINTPTR_MAX-updateOffset+1,image.size(),Mapping));
    for(size_t offset:{updateOffset,eventOffset})for(size_t i=0;i<20;i++) {
        image[offset+i]^=1;mappingRejected=true;
        assert(!MappedEntriesMatch(*profile,base,image.size(),Mapping,&mappingRejected) && !mappingRejected);
        image[offset+i]^=1;
    }
    puts("Firmware fixture identity, layout, bounds and full entry bytes passed");
}

int main(int argc,char **argv) {
    if(argc==10){VerifyFixture(argv);return 0;}
    assert(argc==1);
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
    assert(AdapterMatches(*legacy,false) && AdapterMatches(*legacy,true));
    assert(legacy->prologueSize==16 && MatchEntries(*legacy,update+4,16,event+4,16));
    assert(!MatchEntries(*legacy,update,20,event,20));
    Verify1541Profile();
    puts("Exact identity and full prologue gates passed");
}
