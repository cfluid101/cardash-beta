// Execute the actual image-load gate against synthetic Mach-O mappings carrying
// independent firmware identities/entry bytes. iOS functions are never run.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <notify.h>
#include <sys/mman.h>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
static uint64_t lastReady=0,lastReason=0;
static unsigned hookCalls=0;
static void *FakeStorage(CFTypeRef) {return nullptr;}
static void *HarnessLookup(void *,const char *name) {
    return !strcmp(name,"CMBaseObjectGetDerivedStorage")?(void *)FakeStorage:nullptr;
}
static uint32_t HarnessRegister(const char *name,int *token) {
    *token=strstr(name,"ready_reason")?2:1;return NOTIFY_STATUS_OK;
}
static uint32_t HarnessState(int token,uint64_t state) {
    if(token==2)lastReason=state;else lastReady=state;return NOTIFY_STATUS_OK;
}
#define dlsym HarnessLookup
#define notify_register_check HarnessRegister
#define notify_set_state HarnessState
#import "../native/Loopback.mm"
#undef dlsym
#undef notify_register_check
#undef notify_set_state
extern "C" void CDV3AudioHost(const void *,bool) {}
static void FakeHook(void *,void *,void **original) {++hookCalls;*original=(void *)FakeStorage;}
static unsigned Nibble(char c) {
    if(c>='0' && c<='9')return c-'0';
    if(c>='a' && c<='f')return c-'a'+10;
    if(c>='A' && c<='F')return c-'A'+10;
    assert(false);return 0;
}
static void Decode(const char *text,uint8_t *out,size_t size) {
    assert(strlen(text)==size*2);
    for(size_t i=0;i<size;i++)out[i]=(Nibble(text[i*2])<<4)|Nibble(text[i*2+1]);
}
int main(int argc,char **argv) { @autoreleasepool {
    assert(argc==12);
    const size_t page=(size_t)getpagesize();
    const size_t updateOffset=strtoull(argv[4],nullptr,0),eventOffset=strtoull(argv[5],nullptr,0);
    const size_t imageSize=((eventOffset+64+page-1)/page)*page;
    auto base=(uint8_t *)mmap(nullptr,imageSize,PROT_READ|PROT_WRITE,MAP_ANON|MAP_PRIVATE,-1,0);
    assert(base!=MAP_FAILED);
    mach_header_64 header={};header.magic=MH_MAGIC_64;header.cputype=(cpu_type_t)strtoul(argv[2],nullptr,0);
    header.cpusubtype=(cpu_subtype_t)strtoul(argv[3],nullptr,0);header.filetype=MH_DYLIB;header.ncmds=3;
    const char *name="/System/Library/PrivateFrameworks/APTransport.framework/APTransport";
    const size_t librarySize=(sizeof(dylib_command)+strlen(name)+1+7)&~size_t(7);
    header.sizeofcmds=sizeof(uuid_command)+sizeof(segment_command_64)+(uint32_t)librarySize;
    memcpy(base,&header,sizeof(header));auto command=base+sizeof(header);
    uuid_command uuid={};uuid.cmd=LC_UUID;uuid.cmdsize=sizeof(uuid);Decode(argv[1],uuid.uuid,16);
    if(!strcmp(argv[8],"unknown"))uuid.uuid[0]^=1;
    memcpy(command,&uuid,sizeof(uuid));command+=sizeof(uuid);
    segment_command_64 text={};text.cmd=LC_SEGMENT_64;text.cmdsize=sizeof(text);strcpy(text.segname,"__TEXT");
    text.vmsize=imageSize;text.initprot=VM_PROT_READ|VM_PROT_EXECUTE;
    memcpy(command,&text,sizeof(text));command+=sizeof(text);
    dylib_command library={};library.cmd=LC_ID_DYLIB;library.cmdsize=(uint32_t)librarySize;library.dylib.name.offset=sizeof(library);
    memcpy(command,&library,sizeof(library));strcpy((char *)command+sizeof(library),name);
    Decode(argv[6],base+updateOffset,20);Decode(argv[7],base+eventOffset,20);
    if(!strcmp(argv[8],"changed-entry"))base[eventOffset+19]^=1;
    assert(!mprotect(base,imageSize,PROT_READ|PROT_EXEC));
    HookFunction=FakeHook;
    if(!strcmp(argv[8],"arm64e-adapter"))ImageForAdapter((const mach_header *)base,0,true);
    else Image((const mach_header *)base,0);
    assert(attempted);
    assert(hookCalls==(unsigned)atoi(argv[9]));
    assert((lastReason&0xffff)==(unsigned)atoi(argv[10]));
    assert((lastReady&0xff)==(unsigned)atoi(argv[11]));
    assert(!munmap(base,imageSize));
    puts("Actual loader identity, lifecycle, CPU and prologue gates passed");
} }
