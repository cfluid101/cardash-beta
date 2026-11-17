#define CDV3_VIDEO_BUDGET_TEST 1
#include "../native/VideoBudget.mm"
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include <vector>
static uint32_t request=3000000;
static uint32_t BudgetRequested() {return request;}
static unsigned calls=0;
static CFDictionaryRef Original(uint8_t *) {++calls;return (CFDictionaryRef)CFRetain((__bridge CFDictionaryRef)@{@"Bandwidth":@25000000,@"Other":@7});}
static int32_t Property(CFTypeRef display,CFStringRef,CFAllocatorRef,CFTypeRef *out) {*out=CFRetain(display);return 0;}
static int64_t Read(CFDictionaryRef d) {int64_t value=0;assert(CFNumberGetValue((CFNumberRef)CFDictionaryGetValue(d,CFSTR("Bandwidth")),kCFNumberSInt64Type,&value));return value;}
static CFTypeRef copyValue=nullptr,lastObject=nullptr;
static CFStringRef lastKey=nullptr;
static CFAllocatorRef lastAllocator=nullptr;
static int32_t copyStatus=0;
static unsigned copyCalls=0,derivedCalls=0;
static uint8_t *derivedState=nullptr;
static const uint8_t *readableState=nullptr;
static bool BudgetStateReadable(const uint8_t *state) {return state && state==readableState;}
static int32_t CopyProperty(CFTypeRef object,CFStringRef key,CFAllocatorRef allocator,CFTypeRef *out) {
 ++copyCalls;lastObject=object;lastKey=key;lastAllocator=allocator;
 if (out) *out=copyValue?CFRetain(copyValue):nullptr;
 return copyStatus;
}
static uint8_t *Derived(CFTypeRef object) {assert(object==lastObject);++derivedCalls;return derivedState;}
int main() {@autoreleasepool {
 BudgetOriginal=Original;BudgetDisplayProperty=Property;BudgetUUIDKey=CFSTR("UUID");BudgetBandwidthKey=CFSTR("Bandwidth");
 alignas(16) uint8_t state[0x500]={};state[0x150]=state[0x152]=1;
 *(CFTypeRef *)(state+0x38)=CFSTR("b7e6c5a0-1111-4000-8000-000000000001");
 auto result=BudgetNetworkInfo(state);assert(Read(result)==3000000);assert(CFDictionaryContainsKey(result,CFSTR("Other")));CFRelease(result);
 *(CFTypeRef *)(state+0x38)=CFSTR("unrelated-display");result=BudgetNetworkInfo(state);assert(Read(result)==25000000);CFRelease(result);
 *(CFTypeRef *)(state+0x38)=CFSTR("b7e6c5a0-1111-4000-8000-000000000001");request=0;
 result=BudgetNetworkInfo(state);assert(Read(result)==25000000);CFRelease(result);
 request=3000000;state[0x150]=0;result=BudgetNetworkInfo(state);assert(Read(result)==25000000);CFRelease(result);
 assert(calls==4);

 // The two known firmware entries have different ABIs; unknown UUIDs fail closed.
 uint8_t oldUUID[]={0x9c,0xd9,0x4b,0x73,0xb4,0x7b,0x3b,0x7f,0xa8,0x7e,0xde,0x17,0x6f,0xce,0x84,0x1d};
 uint8_t newUUID[]={0xd4,0xf5,0x2a,0xaa,0x04,0xc2,0x36,0xa9,0xb0,0xef,0x36,0x60,0xc4,0xa7,0x72,0xf6};
 auto oldProfile=CDV3VideoBudgetFindProfile(oldUUID,0x0100000c,0),newProfile=CDV3VideoBudgetFindProfile(newUUID,0x0100000c,0x80000002);
 assert(oldProfile && oldProfile->abi==CDV3VideoBudgetABI::NetworkInfo && oldProfile->offset==0x1215dc);
 assert(newProfile && newProfile->abi==CDV3VideoBudgetABI::CopyProperty && newProfile->offset==0x13f8c4);
 assert(!CDV3VideoBudgetFindProfile(newUUID,0x0100000c,0));
 assert(!CDV3VideoBudgetFindProfile(oldUUID,0x0100000c,0x80000002));
 assert(!CDV3VideoBudgetFindProfile(newUUID,0x01000007,0x80000002));
 newUUID[0]^=1;assert(!CDV3VideoBudgetFindProfile(newUUID,0x0100000c,0x80000002));assert(!CDV3VideoBudgetFindProfile(nullptr,0x0100000c,0));

 // iPhone14,2 / 19E258 uses the same four-argument CopyProperty shape and
 // relevant storage fields as 20A357, but a distinct UUID and entry address.
 uint8_t ios15UUID[]={0x1b,0xfc,0xc2,0x63,0xe0,0xe7,0x3b,0x4d,0xb4,0xda,0x39,0xc0,0xd4,0x6d,0x35,0x94};
 const uint8_t ios15Entry[]={0x7f,0x23,0x03,0xd5,0xff,0x83,0x04,0xd1,0xe9,0x23,0x0c,0x6d,0xfc,0x6f,0x0d,0xa9};
 auto ios15Profile=CDV3VideoBudgetFindProfile(ios15UUID,0x0100000c,0x80000002);
 assert(ios15Profile && "15.4.1 AirPlaySender profile missing");
 assert(ios15Profile->abi==CDV3VideoBudgetABI::CopyProperty);
 // Independent fixture coordinates ensure changing only a UUID cannot pass.
 std::vector<uint8_t> ios15Image(0x127000);
 memcpy(ios15Image.data()+0x1260e4,ios15Entry,sizeof(ios15Entry));
 assert(ios15Profile->offset<=ios15Image.size()-sizeof(ios15Entry));
 assert(!memcmp(ios15Image.data()+ios15Profile->offset,ios15Profile->prologue,sizeof(ios15Entry)));
 assert(!CDV3VideoBudgetFindProfile(ios15UUID,0x0100000c,0));
 assert(!CDV3VideoBudgetFindProfile(ios15UUID,0x0100000c,2));
 assert(!CDV3VideoBudgetFindProfile(ios15UUID,0x01000007,0x80000002));
 ios15UUID[15]^=1;assert(!CDV3VideoBudgetFindProfile(ios15UUID,0x0100000c,0x80000002));

 BudgetOriginalCopyProperty=CopyProperty;BudgetDerivedStorage=Derived;derivedState=state;readableState=state;
 BudgetNetworkInfoKey=CFSTR("NetworkInfo");state[0x150]=state[0x152]=1;
 CFStringRef object=CFSTR("stream-object");CFTypeRef out=nullptr;
 CFDictionaryRef input=(__bridge CFDictionaryRef)@{@"Bandwidth":@25000000,@"Other":@7};copyValue=input;
 // Compare the property by value, not CFString pointer identity. Preserve allocator/args.
 CFStringRef network=CFStringCreateWithCString(kCFAllocatorDefault,"NetworkInfo",kCFStringEncodingUTF8);
 assert(BudgetCopyProperty(object,network,kCFAllocatorSystemDefault,&out)==0);
 assert(copyCalls==1 && derivedCalls==1 && lastObject==object && lastKey==network && lastAllocator==kCFAllocatorSystemDefault);
 assert(out!=input && Read((CFDictionaryRef)out)==3000000 && Read(input)==25000000);
 assert(CFEqual(CFDictionaryGetValue((CFDictionaryRef)out,CFSTR("Other")),CFDictionaryGetValue(input,CFSTR("Other"))));CFRelease(out);
 // Unrelated properties containing a Bandwidth entry must remain untouched.
 assert(BudgetCopyProperty(object,CFSTR("DeviceInfo"),nullptr,&out)==0);assert(out==input && derivedCalls==1);CFRelease(out);
 copyStatus=-123;assert(BudgetCopyProperty(object,network,nullptr,&out)==-123);assert(out==input && derivedCalls==1);CFRelease(out);copyStatus=0;
 assert(BudgetCopyProperty(object,network,nullptr,nullptr)==0 && derivedCalls==1);
 copyValue=nullptr;assert(BudgetCopyProperty(object,network,nullptr,&out)==0 && !out && derivedCalls==1);
 copyValue=CFSTR("not-a-dictionary");assert(BudgetCopyProperty(object,network,nullptr,&out)==0 && out==copyValue && derivedCalls==1);CFRelease(out);
 copyValue=input;request=0;assert(BudgetCopyProperty(object,network,nullptr,&out)==0 && out==input && derivedCalls==1);CFRelease(out);request=3000000;
 *(CFTypeRef *)(state+0x38)=CFSTR("unrelated-display");BudgetCopyProperty(object,network,nullptr,&out);assert(out==input);CFRelease(out);
 *(CFTypeRef *)(state+0x38)=CFSTR("b7e6c5a0-1111-4000-8000-000000000001");
 for (unsigned field:{0x150u,0x152u}) {state[field]=0;BudgetCopyProperty(object,network,nullptr,&out);assert(out==input);CFRelease(out);state[field]=1;}
 for (CFTypeRef value:{(__bridge CFTypeRef)@{@"Bandwidth":@2000000,@"Other":@7},(__bridge CFTypeRef)@{@"Bandwidth":@"bad"},(__bridge CFTypeRef)@{@"Other":@7}}) {
  copyValue=value;BudgetCopyProperty(object,network,nullptr,&out);assert(out==value);CFRelease(out);
 }
 copyValue=input;derivedState=nullptr;BudgetCopyProperty(object,network,nullptr,&out);assert(out==input);CFRelease(out);
 derivedState=(uint8_t *)1;BudgetCopyProperty(object,network,nullptr,&out);assert(out==input);CFRelease(out);
 CFRelease(network);
 puts("Video budget helper and typed CopyProperty ownership, ABI and fallback passed");
}}
